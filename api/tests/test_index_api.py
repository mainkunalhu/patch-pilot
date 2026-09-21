from pathlib import Path

from fastapi.testclient import TestClient

from patchpilot.main import app

client = TestClient(app)
FIXTURE = str(Path(__file__).resolve().parents[2] / "fixtures" / "python-demo")


def test_index_local_fixture():
    r = client.post("/repos/index", json={"local_path": FIXTURE})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["stats"]["files"] == 2
    assert body["stats"]["functions"] == 2
    assert body["stats"]["tests"] == 1
    names = sorted(c["name"] for c in body["chunks"])
    assert names == ["add", "test_add"]


def test_index_requires_source():
    r = client.post("/repos/index", json={})
    assert r.status_code == 400


def test_index_missing_path():
    r = client.post("/repos/index", json={"local_path": "/nope/missing"})
    assert r.status_code == 400
