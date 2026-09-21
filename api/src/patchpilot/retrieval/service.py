"""Shared hybrid-retrieval flow used by POST /query and POST /patch."""

from __future__ import annotations

from dataclasses import dataclass, field

import psycopg

from patchpilot.retrieval.bm25 import bm25_scores
from patchpilot.retrieval.embed import embed_query
from patchpilot.retrieval.hybrid import rank_best_first, rrf_fuse
from patchpilot.retrieval.rewrite import maybe_rewrite_query
from patchpilot.retrieval.store import StoredChunk, fetch_chunks, vector_search


@dataclass
class RankedHunk:
    chunk: StoredChunk
    score: float
    sources: list[str] = field(default_factory=list)


@dataclass
class RetrievalResult:
    query: str
    rewritten: bool
    hunks: list[RankedHunk]


def retrieve_hunks(
    conn: psycopg.Connection, repo_id: str, bug_text: str, top_k: int = 5
) -> RetrievalResult:
    chunks = fetch_chunks(conn, repo_id)
    if not chunks:
        raise LookupError(
            f"repo {repo_id} has no chunks; index it first with POST /repos/index"
        )
    query_text, rewritten = maybe_rewrite_query(bug_text)
    docs = [f"{c.path}\n{c.name}\n{c.content}" for c in chunks]
    bm25_ranking = rank_best_first(bm25_scores(query_text, docs), limit=20)
    qvec = embed_query(query_text)
    vec_hits = vector_search(conn, repo_id, qvec, limit=20)
    id_to_idx = {c.id: i for i, c in enumerate(chunks)}
    vec_ranking = [id_to_idx[h.id] for h in vec_hits if h.id in id_to_idx]

    fused = rrf_fuse([vec_ranking, bm25_ranking])[:top_k]
    vec_set, bm25_set = set(vec_ranking), set(bm25_ranking)
    hunks = []
    for idx, score in fused:
        sources = []
        if idx in vec_set:
            sources.append("vector")
        if idx in bm25_set:
            sources.append("bm25")
        hunks.append(
            RankedHunk(chunk=chunks[idx], score=round(score, 4), sources=sources)
        )
    return RetrievalResult(query=query_text, rewritten=rewritten, hunks=hunks)
