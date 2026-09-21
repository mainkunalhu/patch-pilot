"""Target-repo capability detection: runtime + dependency files.

Pure inspection (no Docker, no network). Heuristics prefer Python when
pytest markers exist so mixed repos (e.g. this monorepo) still resolve
to the Python sandbox. Node detection exists for Track C; the runner
rejects it with a clear message until then.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

PYTHON_DEP_FILES = (
    "requirements.txt",
    "requirements-dev.txt",
    "requirements-test.txt",
    "pyproject.toml",
)

PYTEST_MARKERS = ("pytest.ini", "setup.cfg", "tox.ini")


@dataclass
class RuntimeSpec:
    runtime: str  # "python" | "node"
    dep_files: list[str] = field(default_factory=list)
    test_cmd: list[str] | None = None


def _has_pytest_tests(workdir: Path) -> bool:
    if any((workdir / m).is_file() for m in PYTEST_MARKERS):
        return True
    for pat in ("test_*.py", "*_test.py"):
        try:
            if next(workdir.rglob(pat), None) is not None:
                return True
        except OSError:
            continue
    return False


def _uses_vitest_or_jest(workdir: Path) -> bool:
    pkg = workdir / "package.json"
    if not pkg.is_file():
        return False
    try:
        text = pkg.read_text()
    except OSError:
        return False
    return "vitest" in text or "jest" in text


def detect_runtime(workdir: Path) -> RuntimeSpec:
    dep_files = [f for f in PYTHON_DEP_FILES if (workdir / f).is_file()]
    if _has_pytest_tests(workdir) or dep_files:
        return RuntimeSpec(runtime="python", dep_files=dep_files)
    if _uses_vitest_or_jest(workdir):
        return RuntimeSpec(runtime="node")
    return RuntimeSpec(runtime="python", dep_files=dep_files)
