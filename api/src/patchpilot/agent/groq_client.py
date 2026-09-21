"""Groq coder: proposes unified diffs via openai/gpt-oss-120b.

Raises CoderError (missing key, API failure) — routers map to 503/502.
Tracks prompt/completion tokens and tok/s for the hiring-line proof.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from patchpilot.config import settings

CODER_MODEL = "openai/gpt-oss-120b"

SYSTEM_PROMPT = """You are a bug-fix coder. Given a bug report and the faulty code hunks, output ONLY a unified diff that fixes the bug.

Rules:
- Output the diff and nothing else: no explanations, no prose outside the diff.
- You may wrap the diff in a single ```diff fenced block, or output it raw.
- Use `--- a/<path>` / `+++ b/<path>` headers with paths relative to the repo root.
- EVERY hunk header MUST include line counts: `@@ -<start>,<count> +<start>,<count> @@`.
  Never emit a bare `@@` header — git will reject the patch.
- Keep hunks minimal: only change lines needed to fix the bug.
- Do not rename functions, do not reformat unrelated code.

Example of a valid diff:
--- a/calc.py
+++ b/calc.py
@@ -1,3 +1,2 @@
 def add(a: int, b: int) -> int:
-    # BUG: off-by-one
-    return a + b + 1
+    return a + b
"""


@dataclass
class HunkContext:
    path: str
    name: str
    content: str


@dataclass
class CoderResult:
    raw: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_s: float = 0.0
    attempts: int = 1
    extra: dict = field(default_factory=dict)

    @property
    def tok_s(self) -> float:
        return self.completion_tokens / self.latency_s if self.latency_s > 0 else 0.0


class CoderError(RuntimeError):
    pass


def _hunks_block(hunks: list[HunkContext]) -> str:
    parts = []
    for h in hunks:
        parts.append(f"--- {h.path} :: {h.name} ---\n{h.content}")
    return "\n\n".join(parts)


def generate_patch(
    bug_text: str,
    hunks: list[HunkContext],
    test_log: str | None = None,
    extra_context: str | None = None,
) -> CoderResult:
    """One coder call. For repair retries pass the validator/test failure
    in test_log — the model sees what went wrong last attempt."""
    if not settings.groq_api_key.strip():
        raise CoderError("GROQ_API_KEY is not set. Export it to use the coder agent.")
    user_parts = [
        f"BUG REPORT:\n{bug_text}",
        f"FAULTY HUNKS:\n{_hunks_block(hunks)}",
    ]
    if test_log:
        user_parts.append(f"PREVIOUS ATTEMPT FAILED:\n{test_log}\nFix the diff.")
    if extra_context:
        user_parts.append(f"EXTRA CONTEXT:\n{extra_context}")

    from groq import Groq

    client = Groq(api_key=settings.groq_api_key)
    start = time.perf_counter()
    try:
        resp = client.chat.completions.create(
            model=CODER_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": "\n\n".join(user_parts)},
            ],
            temperature=0.2,
            max_tokens=2048,
        )
    except Exception as e:
        raise CoderError(f"Groq coder call failed: {e}") from e
    latency = time.perf_counter() - start
    usage = getattr(resp, "usage", None)
    content = (resp.choices[0].message.content or "").strip()
    if not content:
        raise CoderError("Groq coder returned empty response")
    return CoderResult(
        raw=content,
        prompt_tokens=(usage.prompt_tokens if usage else 0) or 0,
        completion_tokens=(usage.completion_tokens if usage else 0) or 0,
        latency_s=latency,
    )
