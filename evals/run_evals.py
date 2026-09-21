"""SWE-style eval harness: baseline must fail → /runs must fix → report.

Usage:
  uv run --project api python evals/run_evals.py --limit 5   # eval-quick
  uv run --project api python evals/run_evals.py             # full dataset

Requires the full stack: API on --api, Postgres, Ollama, Docker,
GROQ_API_KEY (root .env works). Primary verdict is the sandbox proof
from POST /runs; DeepEval GEval correctness is a secondary signal and
never flips a sandbox verdict.
"""

from __future__ import annotations

import argparse
import datetime
import json
import statistics
import sys
import tempfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "api" / "src"))
sys.path.insert(0, str(ROOT / "evals"))

from patchpilot.sandbox.runner import run_tests  # noqa: E402


def load_dataset(path: Path, limit: int | None) -> list[dict]:
    cases = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            cases.append(json.loads(line))
    return cases[:limit] if limit else cases


def materialize(case: dict) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix=f"eval-{case['id']}-"))
    for rel, content in case["files"].items():
        p = tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    return tmp


def judge_correctness(bug_text: str, diff: str | None) -> float | None:
    """DeepEval GEval score 0..1, or None when judging is unavailable."""
    if not diff:
        return 0.0
    try:
        from deepeval.metrics import GEval
        from deepeval.test_case import LLMTestCase, SingleTurnParams

        from deepeval_groq import GroqJudgeLLM

        metric = GEval(
            name="PatchCorrectness",
            criteria="Score whether the actual output (a unified diff) "
            "fixes the bug described in the input. Ignore style; only "
            "correctness matters.",
            evaluation_params=[
                SingleTurnParams.INPUT,
                SingleTurnParams.ACTUAL_OUTPUT,
            ],
            model=GroqJudgeLLM(),
            threshold=0.5,
        )
        tc = LLMTestCase(input=bug_text, actual_output=diff)
        metric.measure(tc)
        return metric.score
    except Exception as e:  # noqa: BLE001 - judging is best-effort
        print(f"    [judge skipped: {e}]")
        return None


def run_case(api: str, case: dict, timeout_s: int) -> dict:
    repo_dir = materialize(case)
    result: dict = {"id": case["id"], "fail_to_pass": case.get("fail_to_pass", [])}

    base = run_tests(repo_dir, diff=None, timeout_s=timeout_s)
    result["baseline_passed"] = base.passed
    if base.passed:
        result["verdict"] = "invalid_case"
        result["reason"] = "tests already pass without a patch"
        return result

    try:
        r = httpx.post(
            f"{api}/repos/index",
            json={"local_path": str(repo_dir), "persist": True},
            timeout=120,
        )
        r.raise_for_status()
        repo_id = r.json()["repo_id"]
        r = httpx.post(
            f"{api}/runs",
            json={
                "repo_id": repo_id,
                "bug_text": case["bug_text"],
                "timeout_s": timeout_s,
            },
            timeout=600,
        )
        r.raise_for_status()
        run = r.json()
    except httpx.HTTPError as e:
        result["verdict"] = "error"
        result["reason"] = f"API error: {e}"
        return result

    fixed = run["status"] == "fixed"
    result.update(
        {
            "verdict": "fixed" if fixed else run["status"],
            "run_id": run["run_id"],
            "attempts": run["attempts"],
            "tokens_per_sec": run["usage"]["tokens_per_sec"],
            "has_diff": bool(run["diff"]),
        }
    )
    if fixed:
        result["geval_score"] = judge_correctness(case["bug_text"], run["diff"])
    return result


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", default=str(ROOT / "evals" / "dataset.jsonl"))
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--api", default="http://localhost:8000")
    p.add_argument("--timeout", type=int, default=120)
    p.add_argument("--out", default=str(ROOT / "evals" / "results"))
    args = p.parse_args()

    try:
        health = httpx.get(f"{args.api}/health", timeout=10).json()
        assert health.get("status") == "ok"
    except Exception as e:  # noqa: BLE001
        print(f"API at {args.api} unreachable: {e}")
        return 2

    cases = load_dataset(Path(args.dataset), args.limit)
    print(f"Running {len(cases)} eval cases against {args.api}")
    results = []
    for case in cases:
        print(f"[{case['id']}] {case['bug_text'][:60]}…")
        res = run_case(args.api, case, args.timeout)
        print(f"  → {res['verdict']}", end="")
        if res.get("tokens_per_sec") is not None:
            print(f" ({res['tokens_per_sec']} tok/s)", end="")
        if res.get("geval_score") is not None:
            print(f" geval={res['geval_score']:.2f}", end="")
        print()
        results.append(res)

    valid = [r for r in results if r["verdict"] not in ("invalid_case", "error")]
    fixed = [r for r in results if r["verdict"] == "fixed"]
    fix_rate = (len(fixed) / len(valid) * 100) if valid else 0.0
    tokss = [r["tokens_per_sec"] for r in fixed if r.get("tokens_per_sec")]
    summary = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "total": len(results),
        "valid": len(valid),
        "fixed": len(fixed),
        "fix_rate_pct": round(fix_rate, 1),
        "median_tok_s": round(statistics.median(tokss), 1) if tokss else None,
        "results": results,
    }
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"eval-{summary['timestamp'][:19].replace(':', '-')}.json"
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"\nfix-rate: {len(fixed)}/{len(valid)} ({summary['fix_rate_pct']}%)")
    print(f"median tok/s: {summary['median_tok_s']}")
    print(f"report: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
