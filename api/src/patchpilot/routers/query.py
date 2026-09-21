from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from patchpilot.retrieval.bm25 import bm25_scores
from patchpilot.retrieval.embed import EmbedError, embed_query
from patchpilot.retrieval.hybrid import rank_best_first, rrf_fuse
from patchpilot.retrieval.rewrite import maybe_rewrite_query
from patchpilot.retrieval.store import (
    StoreError,
    connect,
    fetch_chunks,
    vector_search,
)

router = APIRouter()


class QueryRequest(BaseModel):
    repo_id: str
    bug_text: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


class HunkOut(BaseModel):
    path: str
    lang: str
    name: str
    content: str
    is_test: bool
    start_line: int | None
    end_line: int | None
    score: float
    sources: list[str]


class QueryResponse(BaseModel):
    repo_id: str
    query: str
    rewritten: bool
    hunks: list[HunkOut]


@router.post("/query", response_model=QueryResponse)
def query_repo(body: QueryRequest):
    try:
        conn = connect()
    except StoreError as e:
        raise HTTPException(status_code=503, detail=str(e))
    with conn:
        try:
            chunks = fetch_chunks(conn, body.repo_id)
        except StoreError as e:
            raise HTTPException(status_code=503, detail=str(e))
        if not chunks:
            raise HTTPException(
                status_code=404,
                detail=f"repo {body.repo_id} has no chunks; "
                "index it first with POST /repos/index",
            )
        query_text, rewritten = maybe_rewrite_query(body.bug_text)
        docs = [f"{c.path}\n{c.name}\n{c.content}" for c in chunks]
        bm25_ranking = rank_best_first(bm25_scores(query_text, docs), limit=20)
        try:
            qvec = embed_query(query_text)
            vec_hits = vector_search(conn, body.repo_id, qvec, limit=20)
        except (StoreError, EmbedError) as e:
            raise HTTPException(status_code=503, detail=str(e))
        id_to_idx = {c.id: i for i, c in enumerate(chunks)}
        vec_ranking = [id_to_idx[h.id] for h in vec_hits if h.id in id_to_idx]

        fused = rrf_fuse([vec_ranking, bm25_ranking])[: body.top_k]
        vec_set, bm25_set = set(vec_ranking), set(bm25_ranking)
        hunks = []
        for idx, score in fused:
            c = chunks[idx]
            sources = []
            if idx in vec_set:
                sources.append("vector")
            if idx in bm25_set:
                sources.append("bm25")
            hunks.append(
                HunkOut(
                    path=c.path,
                    lang=c.lang,
                    name=c.name,
                    content=c.content,
                    is_test=c.is_test,
                    start_line=c.start_line,
                    end_line=c.end_line,
                    score=round(score, 4),
                    sources=sources,
                )
            )
        return QueryResponse(
            repo_id=body.repo_id, query=query_text, rewritten=rewritten, hunks=hunks
        )
