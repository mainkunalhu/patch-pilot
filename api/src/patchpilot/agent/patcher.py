"""Patch validation: extract → git apply --check → syntax re-parse.

Validation runs against a temp COPY of the repo, never the original.
Two gates:
  1. `git apply --check` — diff applies cleanly.
  2. tree-sitter re-parse of every changed .py file — no syntax errors.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import tree_sitter_python as tspython
from tree_sitter import Language, Parser

PY_LANGUAGE = Language(tspython.language())

_FENCE = re.compile(r"```(?:diff)?\s*\n(.*?)```", re.DOTALL)
_PLUSPLUS = re.compile(r"^\+\+\+\s+b/(.+)$", re.MULTILINE)


@dataclass
class Validation:
    ok: bool
    diff: str = ""
    error: str = ""
    changed_files: list[str] | None = None

    def __post_init__(self):
        if self.changed_files is None:
            self.changed_files = []


def extract_diff(raw: str) -> str:
    """Pull the diff out of a ```diff fence, else use the raw text.
    Strips prose lines before the first `--- ` / `diff --git` header."""
    m = _FENCE.search(raw)
    text = m.group(1).strip() if m else raw.strip()
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith(("--- ", "diff --git ")):
            return "\n".join(lines[i:]).strip() + "\n"
    return text + "\n"


def changed_paths(diff: str) -> list[str]:
    return _PLUSPLUS.findall(diff)


def _git_apply_check(workdir: Path, diff: str) -> str | None:
    r = subprocess.run(
        ["git", "apply", "--check", "-"],
        input=diff,
        text=True,
        capture_output=True,
        cwd=workdir,
        timeout=30,
        check=False,
    )
    if r.returncode != 0:
        return (r.stderr or r.stdout or "git apply --check failed").strip()
    return None


def _syntax_errors(workdir: Path, paths: list[str]) -> list[str]:
    parser = Parser(PY_LANGUAGE)
    errors = []
    for rel in paths:
        if not rel.endswith(".py"):
            continue
        p = workdir / rel
        if not p.is_file():
            continue
        try:
            tree = parser.parse(p.read_bytes())
        except Exception:  # noqa: BLE001 - treat parse crash as error text
            errors.append(f"{rel}: parser crashed")
            continue
        if tree.root_node.has_error:
            errors.append(f"{rel}: syntax error after patch")
    return errors


def validate_patch(workdir: Path, raw: str) -> Validation:
    diff = extract_diff(raw)
    if not diff.strip():
        return Validation(ok=False, error="empty diff")
    paths = changed_paths(diff)
    if not paths:
        return Validation(
            ok=False, diff=diff, error="no +++ b/<path> file headers found"
        )
    with tempfile.TemporaryDirectory(prefix="patchpilot-validate-") as tmp:
        copy = Path(tmp) / "repo"
        shutil.copytree(
            workdir,
            copy,
            ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv"),
        )
        err = _git_apply_check(copy, diff)
        if err:
            return Validation(ok=False, diff=diff, error=err, changed_files=paths)
        r = subprocess.run(
            ["git", "apply", "-"],
            input=diff,
            text=True,
            capture_output=True,
            cwd=copy,
            timeout=30,
            check=False,
        )
        if r.returncode != 0:
            return Validation(
                ok=False,
                diff=diff,
                error=(r.stderr or "git apply failed").strip(),
                changed_files=paths,
            )
        syn_errs = _syntax_errors(copy, paths)
        if syn_errs:
            return Validation(
                ok=False, diff=diff, error="; ".join(syn_errs), changed_files=paths
            )
    return Validation(ok=True, diff=diff, changed_files=paths)
