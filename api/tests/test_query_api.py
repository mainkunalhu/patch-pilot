"""DB-backed hybrid retrieval tests. Skipped when Postgres or Ollama
is unreachable (e.g. CI without services). Run locally with:
  make db-direct  (then apply infra/sql/001_schema.sql)
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from patchpilot.main import app
from patchpilot.retrieval.embed import EmbedError, embed_query
from patchpilot.retrieval.store import StoreError, connect

client = TestClient(app)
FIXTURE = str(Path(__file__).resolve().parents[2] / "fixtures" / "python-demo")


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


def test_index_persist_then_query_finds_faulty_function(monkeypatch):
    _need_services()
    # Deterministic: disable rewrite so ranking (not the LLM) is under test.
    monkeypatch.setattr("patchpilot.config.settings.groq_api_key", "")
    r = client.post("/repos/index", json={"local_path": FIXTURE, "persist": True})
    assert r.status_code == 200, r.text
    repo_id = r.json()["repo_id"]
    assert r.json()["persisted"] is True

    r = client.post(
        "/query",
        json={
            "repo_id": repo_id,
            "bug_text": "add function returns wrong sum, off by one",
            "top_k": 5,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rewritten"] is False  # rewrite disabled above
    names = [h["name"] for h in body["hunks"]]
    assert "add" in names
    assert names[0] == "add"
    assert all(h["sources"] for h in body["hunks"])


def test_query_unknown_repo_404():
    _need_services()
    r = client.post("/query", json={"repo_id": "repo_doesnotexist", "bug_text": "boom"})
    assert r.status_code == 404
