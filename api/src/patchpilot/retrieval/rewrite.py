"""Bug-text → code-oriented query rewrite via Groq (llama-3.1-8b-instant).

Optional by design: without GROQ_API_KEY the raw bug text is used
unchanged (rewritten=False), so dev/CI never hard-depends on Groq.
"""

from __future__ import annotations

from patchpilot.config import settings

REWRITE_MODEL = "llama-3.1-8b-instant"


def maybe_rewrite_query(bug_text: str) -> tuple[str, bool]:
    """Return (query, rewritten). Never raises: any Groq failure falls
    back to the raw bug text."""
    if not settings.groq_api_key.strip():
        return bug_text, False
    try:
        from groq import Groq

        client = Groq(api_key=settings.groq_api_key)
        resp = client.chat.completions.create(
            model=REWRITE_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Rewrite the bug report as a short code-search query: "
                        "likely function names, identifiers, and error keywords. "
                        "Reply with the query only, no explanation."
                    ),
                },
                {"role": "user", "content": bug_text},
            ],
            max_tokens=128,
            temperature=0,
        )
        rewritten = (resp.choices[0].message.content or "").strip()
        return (rewritten or bug_text, bool(rewritten))
    except Exception:  # noqa: BLE001 - Groq must never break retrieval
        return bug_text, False
