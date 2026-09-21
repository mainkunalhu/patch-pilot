"""Repo ingest: resolve a local path or public git URL to a working snapshot.

Phase 1 is DB-free: returns a content-addressed snapshot on disk.
Phase 2 will persist repos/chunks into Postgres+pgvector.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RepoSnapshot:
    repo_id: str
    workdir: Path
    sha: str | None
    source: str
    cleanup: bool = False

    def dispose(self) -> None:
        if self.cleanup and self.workdir.exists():
            shutil.rmtree(self.workdir, ignore_errors=True)


def _repo_id(source: str, sha: str | None) -> str:
    h = hashlib.sha256(f"{source}@{sha or ''}".encode()).hexdigest()[:12]
    return f"repo_{h}"


def _git(args: list[str], cwd: Path | None = None) -> str:
    r = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if r.returncode != 0:
        raise ValueError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def resolve_source(
    *,
    git_url: str | None = None,
    local_path: str | None = None,
    sha: str | None = None,
) -> RepoSnapshot:
    """Resolve exactly one of git_url / local_path to a snapshot."""
    if bool(git_url) == bool(local_path):
        raise ValueError("provide exactly one of git_url or local_path")

    if local_path:
        p = Path(local_path).expanduser()
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        if not p.exists():
            raise ValueError(f"local_path does not exist: {p}")
        if not p.is_dir():
            raise ValueError(f"local_path is not a directory: {p}")
        actual_sha = None
        if (p / ".git").exists():
            try:
                actual_sha = _git(["rev-parse", "HEAD"], cwd=p)
            except ValueError:
                actual_sha = None
        rid = _repo_id(str(p), sha or actual_sha)
        return RepoSnapshot(
            repo_id=rid, workdir=p, sha=sha or actual_sha, source=str(p)
        )

    assert git_url is not None
    tmp = Path(tempfile.mkdtemp(prefix="patchpilot-"))
    _git(["clone", "--depth", "1", git_url, str(tmp / "repo")])
    workdir = tmp / "repo"
    if sha:
        _git(["fetch", "origin", sha], cwd=workdir)
        _git(["checkout", sha], cwd=workdir)
    actual_sha = _git(["rev-parse", "HEAD"], cwd=workdir)
    rid = _repo_id(git_url, actual_sha)
    return RepoSnapshot(
        repo_id=rid, workdir=workdir, sha=actual_sha, source=git_url, cleanup=True
    )


SKIP_DIRS = {".git", ".venv", "__pycache__", "node_modules", ".next", "dist"}


def iter_python_files(workdir: Path) -> list[Path]:
    files: list[Path] = []
    for p in sorted(workdir.rglob("*.py")):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        files.append(p)
    return files
