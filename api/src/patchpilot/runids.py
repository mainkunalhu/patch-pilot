"""Run ID generation (Phase 3; runs table owned by retrieval.store)."""

from __future__ import annotations

import uuid


def new_run_id() -> str:
    return f"run_{uuid.uuid4().hex[:12]}"
