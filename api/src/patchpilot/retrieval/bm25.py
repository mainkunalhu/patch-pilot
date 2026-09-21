"""BM25 lexical search over chunk contents (rank-bm25)."""

from __future__ import annotations

import re

from rank_bm25 import BM25Okapi

_TOKEN = re.compile(r"[a-z0-9_]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def bm25_scores(query: str, docs: list[str]) -> list[float]:
    """Score each doc against the query. Empty query/docs → zeros."""
    if not docs or not query.strip():
        return [0.0] * len(docs)
    bm25 = BM25Okapi([tokenize(d) for d in docs])
    return list(bm25.get_scores(tokenize(query)))
