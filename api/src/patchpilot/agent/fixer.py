"""Fixer loop: propose → validate → sandbox-test → retry (max 3x).

Each round feeds the previous failure (validator error or test log)
back to the coder. First round with passing tests wins. Totals token
usage across rounds for the hiring-line proof.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from patchpilot.agent.coder import HunkContext, propose_patch
from patchpilot.sandbox.runner import TestResult, run_tests


@dataclass
class FixResult:
    status: str  # fixed | tests_failed | patch_invalid
    diff: str | None = None
    test_log: str | None = None
    attempts: int = 0
    flaky: bool = False
    prompt_tokens: int = 0
    completion_tokens: int = 0
    tok_s: float = 0.0


def fix_loop(
    workdir: Path,
    bug_text: str,
    hunks: list[HunkContext],
    max_attempts: int = 3,
    timeout_s: int = 180,
) -> FixResult:
    feedback: str | None = None
    prompt_tokens = completion_tokens = 0
    weighted_latency = 0.0
    last_diff: str | None = None
    last_log: str | None = None
    rounds = 0

    for _ in range(max(1, max_attempts)):
        rounds += 1
        proposal = propose_patch(workdir, bug_text, hunks, test_log=feedback)
        prompt_tokens += proposal.result.prompt_tokens
        completion_tokens += proposal.result.completion_tokens
        weighted_latency += proposal.result.latency_s
        v = proposal.validation
        if not v.ok:
            last_diff, last_log = v.diff or None, None
            feedback = f"Validator rejected the diff:\n{v.error}"
            continue
        last_diff = v.diff
        test: TestResult = run_tests(workdir, diff=v.diff, timeout_s=timeout_s)
        last_log = test.log
        if test.passed:
            tok_s = completion_tokens / weighted_latency if weighted_latency else 0.0
            return FixResult(
                status="fixed",
                diff=v.diff,
                test_log=test.log,
                attempts=rounds,
                flaky=test.flaky,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                tok_s=tok_s,
            )
        feedback = f"Sandbox tests failed:\n{test.log}"
        last_diff = v.diff

    tok_s = completion_tokens / weighted_latency if weighted_latency else 0.0
    return FixResult(
        status="tests_failed" if last_log else "patch_invalid",
        diff=last_diff,
        test_log=last_log,
        attempts=rounds,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        tok_s=tok_s,
    )
