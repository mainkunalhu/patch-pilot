"""POST /runs tests with a stubbed coder (no GROQ_API_KEY needed).

Needs Postgres + Ollama + Docker. The stub proves the fixer loop,
sandbox proof, and run persistence; the real coder is covered in
Phase 3 live verification.
"""

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from patchpilot.agent.coder import Proposal
from patchpilot.agent.groq_client import CoderResult
from patchpilot.agent.patcher import Validation
from patchpilot.main import app
from patchpilot.retrieval.embed import EmbedError, embed_query
from patchpilot.retrieval.store import StoreError, connect

client = TestClient(app)
FIXTURE = str(Path(__file__).resolve().parents[2] / "fixtures" / "python-demo")

GOOD_DIFF = """--- a/calc.py
+++ b/calc.py
@@ -1,3 +1,2 @@
 def add(a: int, b: int) -> int:
-    # BUG: off-by-one for demo purposes (Phase 1 fixture)
-    return a + b + 1
+    return a + b
"""

COMMENT_ONLY_DIFF = """--- a/calc.py
+++ b/calc.py
@@ -1,3 +1,3 @@
 def add(a: int, b: int) -> int:
-    # BUG: off-by-one for demo purposes (Phase 1 fixture)
+    # still buggy
     return a + b + 1
"""


def _need_services():
    try:
        conn = connect()
        conn.close()
    except StoreError as e:
        pytest.skip(f"Postgres unreachable: {e}")
    try:
        embed_query("connectivity probe")
    except EmbedError as e:
        pytest.skip(f"Ollama unreachable: {e}")
    r = subprocess.run(["docker", "info"], capture_output=True, timeout=30, check=False)
    if r.returncode != 0:
        pytest.skip("Docker daemon unreachable")


def _indexed_repo_id() -> str:
    r = client.post("/repos/index", json={"local_path": FIXTURE, "persist": True})
    assert r.status_code == 200, r.text
    return r.json()["repo_id"]


def _stub_propose(diff: str):
    def fake(workdir, bug_text, hunks, test_log=None, max_attempts=2):
        return Proposal(
            validation=Validation(ok=True, diff=diff, changed_files=["calc.py"]),
            result=CoderResult(
                raw=diff, prompt_tokens=10, completion_tokens=5, latency_s=0.05
            ),
            attempts=1,
        )

    return fake


def test_runs_fixed_with_proof(monkeypatch):
    _need_services()
    monkeypatch.setattr(
        "patchpilot.agent.fixer.propose_patch", _stub_propose(GOOD_DIFF)
    )
    repo_id = _indexed_repo_id()
    r = client.post(
        "/runs",
        json={
            "repo_id": repo_id,
            "bug_text": "add is off by one",
            "timeout_s": 60,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "fixed"
    assert body["diff"] == GOOD_DIFF
    assert body["attempts"] == 1
    assert "1 passed" in (body["test_log"] or "")

    proof = client.get(f"/runs/{body['run_id']}")
    assert proof.status_code == 200
    assert proof.json()["status"] == "fixed"
    assert proof.json()["diff"] == GOOD_DIFF


def test_runs_tests_failed_when_patch_does_not_fix(monkeypatch):
    _need_services()
    monkeypatch.setattr(
        "patchpilot.agent.fixer.propose_patch", _stub_propose(COMMENT_ONLY_DIFF)
    )
    repo_id = _indexed_repo_id()
    r = client.post(
        "/runs",
        json={
            "repo_id": repo_id,
            "bug_text": "add is off by one",
            "max_attempts": 1,
            "timeout_s": 60,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "tests_failed"
    assert body["attempts"] == 1
    assert "assert 4 == 3" in (body["test_log"] or "")


def test_runs_unknown_run_404():
    _need_services()
    r = client.get("/runs/run_nope123456")
    assert r.status_code == 404


def test_fix_loop_wires_real_propose_patch(monkeypatch):
    """Regression: fix_loop must call propose_patch with a compatible
    signature. Stubs only the Groq call; validation + sandbox are real."""
    from patchpilot.agent import coder as coder_module
    from patchpilot.agent.coder import HunkContext
    from patchpilot.agent.fixer import fix_loop

    r = subprocess.run(["docker", "info"], capture_output=True, timeout=30, check=False)
    if r.returncode != 0:
        pytest.skip("Docker daemon unreachable")

    calls: list = []

    def fake_generate(bug_text, hunks, test_log=None, extra_context=None):
        calls.append(test_log)
        return CoderResult(
            raw=GOOD_DIFF, prompt_tokens=10, completion_tokens=5, latency_s=0.05
        )

    monkeypatch.setattr(coder_module, "generate_patch", fake_generate)
    fix = fix_loop(
        Path(FIXTURE),
        "add is off by one",
        [HunkContext(path="calc.py", name="add", content="def add")],
        max_attempts=3,
        timeout_s=60,
    )
    assert fix.status == "fixed", fix.test_log
    assert calls == [None]
    assert fix.attempts == 1
