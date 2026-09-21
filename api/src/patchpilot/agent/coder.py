"""Coder orchestration: generate → validate → repair (max 2 attempts).

Single-proposal flow for POST /patch. The sandbox test loop (max 3x)
lives in Phase 4 and reuses this via test_log feedback.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from patchpilot.agent.groq_client import (
    CoderError,
    CoderResult,
    HunkContext,
    generate_patch,
)
from patchpilot.agent.patcher import Validation, validate_patch


@dataclass
class Proposal:
    validation: Validation
    result: CoderResult
    attempts: int


def propose_patch(
    workdir: Path,
    bug_text: str,
    hunks: list[HunkContext],
    test_log: str | None = None,
    max_attempts: int = 2,
) -> Proposal:
    last_result: CoderResult | None = None
    last_validation: Validation | None = None
    attempts = 0
    for _ in range(max(1, max_attempts)):
        attempts += 1
        last_result = generate_patch(bug_text, hunks, test_log=test_log)
        last_validation = validate_patch(workdir, last_result.raw)
        if last_validation.ok:
            break
        test_log = (
            f"Validator rejected the diff:\n{last_validation.error}\n"
            "Remember: output a valid unified diff with "
            "`--- a/<path>` / `+++ b/<path>` headers and hunk headers like "
            "`@@ -1,3 +1,2 @@` (line counts required)."
        )
    assert last_result is not None and last_validation is not None
    if attempts > 1:
        last_result.attempts = attempts
    return Proposal(
        validation=last_validation, result=last_result, attempts=attempts
    )


__all__ = ["CoderError", "HunkContext", "Proposal", "propose_patch"]
