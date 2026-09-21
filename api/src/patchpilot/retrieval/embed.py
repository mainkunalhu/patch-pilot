"""Local embeddings via Ollama (nomic-embed-text, 768-dim).

Batch embeds with an in-process cache keyed by text hash so re-indexing
a repo doesn't re-pay embedding costs. Raises EmbedError with a clear
message when Ollama is unreachable (caller maps to 503).
"""

from __future__ import annotations

import hashlib

import httpx

from patchpilot.config import settings

DIM = 768
_cache: dict[str, list[float]] = {}


class EmbedError(RuntimeError):
    pass


def _key(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    missing = [t for t in texts if _key(t) not in _cache]
    if missing:
        try:
            r = httpx.post(
                f"{settings.ollama_host}/api/embed",
                json={"model": settings.embed_model, "input": missing},
                timeout=120,
            )
            r.raise_for_status()
            vecs = r.json()["embeddings"]
        except (httpx.HTTPError, KeyError) as e:
            raise EmbedError(
                f"Ollama embed failed at {settings.ollama_host} "
                f"(model={settings.embed_model}): {e}. "
                "Is ollama running? `ollama pull nomic-embed-text`"
            ) from e
        if any(len(v) != DIM for v in vecs):
            raise EmbedError(f"expected {DIM}-dim embeddings, got {len(vecs[0])}")
        for t, v in zip(missing, vecs):
            _cache[_key(t)] = v
    return [_cache[_key(t)] for t in texts]


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]


def clear_cache() -> None:
    _cache.clear()
