"""POST /patch tests.

- No-key 503 path is DB-gated (router hits retrieval before the coder).
- Mocked-coder test proves router + runs-table logging without a key.
Run locally with: make db-direct (+ apply infra/sql/001_schema.sql).
"""

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


def _indexed_repo_id() -> str:
    r = client.post("/repos/index", json={"local_path": FIXTURE, "persist": True})
    assert r.status_code == 200, r.text
    return r.json()["repo_id"]


def test_patch_without_key_returns_503():
    _need_services()
    repo_id = _indexed_repo_id()
    r = client.post("/patch", json={"repo_id": repo_id, "bug_text": "off by one"})
    assert r.status_code == 503
    assert "GROQ_API_KEY" in r.json()["detail"]


def test_patch_with_mocked_coder_logs_run(monkeypatch):
    _need_services()

    def fake_propose(workdir, bug_text, hunks, max_attempts=2):
        assert hunks, "coder should receive retrieved hunks"
        return Proposal(
            validation=Validation(ok=True, diff=GOOD_DIFF, changed_files=["calc.py"]),
            result=CoderResult(
                raw="```diff\n" + GOOD_DIFF + "```",
                prompt_tokens=100,
                completion_tokens=50,
                latency_s=0.1,
            ),
            attempts=1,
        )

    monkeypatch.setattr("patchpilot.routers.patches.propose_patch", fake_propose)
    repo_id = _indexed_repo_id()
    r = client.post(
        "/patch", json={"repo_id": repo_id, "bug_text": "add is off by one"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["valid"] is True
    assert body["diff"] == GOOD_DIFF
    assert body["attempts"] == 1
    assert body["usage"]["prompt_tokens"] == 100
    assert body["usage"]["tokens_per_sec"] == 500.0
    assert body["run_id"].startswith("run_")

    conn = connect()
    with conn:
        row = conn.execute(
            "SELECT status, prompt_tokens, completion_tokens, tokens_per_sec"
            " FROM runs WHERE id = %s",
            (body["run_id"],),
        ).fetchone()
    assert row is not None
    assert row[0] == "patch_proposed"
    assert (row[1], row[2]) == (100, 50)
