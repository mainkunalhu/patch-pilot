"""Patch validation: extract → normalize headers → git apply --check → re-parse.

Validation runs against a temp COPY of the repo, never the original.
Three gates:
  1. Hunk headers recounted from bodies (small-model count errors fixed).
  2. `git apply --check` — diff applies cleanly.
  3. tree-sitter re-parse of every changed .py file — no syntax errors.
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
_HUNK = re.compile(r"^@@(?:\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?)?\s*@@(.*)$")


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


def normalize_hunk_headers(diff: str) -> str:
    """Recount `@@ -a,b +c,d @@` headers from hunk bodies.

    Small coder models routinely emit wrong line counts (or bare `@@`).
    Counts are deterministic given the body, so fix them instead of
    rejecting: old = context + removed, new = context + added. Start
    lines are kept when present, else tracked sequentially from 1,1.
    """
    out: list[str] = []
    old_start, new_start = 1, 1
    header: re.Match | None = None
    tail = ""
    body_old = body_new = 0
    body: list[str] = []

    def flush() -> None:
        nonlocal old_start, new_start, header, tail, body_old, body_new, body
        if header is None:
            return
        if header.group(1) is not None:
            old_start = int(header.group(1))
        if header.group(3) is not None:
            new_start = int(header.group(3))
        out.append(f"@@ -{old_start},{body_old} +{new_start},{body_new} @@{tail}")
        out.extend(body)
        old_start += body_old
        new_start += body_new
        header, tail, body_old, body_new, body = None, "", 0, 0, []

    for line in diff.splitlines():
        if line.strip() == "@@":
            line = "@@ @@"
        m = _HUNK.match(line)
        if m:
            flush()
            header, tail = m, m.group(5) or ""
            continue
        if header is not None and line.startswith(("--- ", "+++ ", "diff --git ")):
            flush()
            out.append(line)
            continue
        if header is not None:
            if not line.startswith("\\"):
                if line.startswith((" ", "-")):
                    body_old += 1
                if line.startswith((" ", "+")):
                    body_new += 1
            body.append(line)
        else:
            out.append(line)
    flush()
    return "\n".join(out) + "\n"


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
    diff = normalize_hunk_headers(extract_diff(raw))
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
