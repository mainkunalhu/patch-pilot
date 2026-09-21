"""Hybrid fusion: reciprocal rank fusion (RRF) of vector + BM25 rankings."""

from __future__ import annotations

RRF_K = 60


def rrf_fuse(rankings: list[list[int]], k: int = RRF_K) -> list[tuple[int, float]]:
    """Fuse multiple rankings (lists of item idx, best-first) into
    [(idx, score)] sorted best-first. Items missing from a ranking
    simply get no contribution from it."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)


def rank_best_first(scores: list[float], limit: int | None = None) -> list[int]:
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    return order[:limit] if limit is not None else order
