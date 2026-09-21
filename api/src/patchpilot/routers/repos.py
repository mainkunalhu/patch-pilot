from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from patchpilot.indexer import chunk_workdir, naive_chunk
from patchpilot.ingest import iter_python_files, resolve_source
from patchpilot.retrieval.embed import EmbedError, embed_texts
from patchpilot.retrieval.store import (
    StoreError,
    connect,
    embed_text_for,
    replace_chunks,
    upsert_repo,
)

router = APIRouter()


class IndexRequest(BaseModel):
    git_url: str | None = Field(default=None)
    local_path: str | None = Field(default=None)
    sha: str | None = Field(default=None)
    persist: bool = Field(
        default=True,
        description="Embed chunks and upsert into Postgres+pgvector. "
        "Set false for AST-only indexing without DB/Ollama.",
    )


class ChunkOut(BaseModel):
    path: str
    lang: str
    name: str
    signature: str
    content: str
    is_test: bool
    start_line: int
    end_line: int


class IndexStats(BaseModel):
    files: int
    functions: int
    tests: int
    naive_chunks: int


class IndexResponse(BaseModel):
    repo_id: str
    sha: str | None
    source: str
    persisted: bool
    chunks: list[ChunkOut]
    stats: IndexStats


def _persist(repo_id: str, source: str, sha: str | None, chunks) -> None:
    try:
        conn = connect()
    except StoreError as e:
        raise HTTPException(status_code=503, detail=str(e))
    with conn:
        try:
            upsert_repo(conn, repo_id, source, sha)
            if chunks:
                vecs = embed_texts([embed_text_for(c) for c in chunks])
                replace_chunks(conn, repo_id, chunks, vecs)
            else:
                replace_chunks(conn, repo_id, [], [])
        except (StoreError, EmbedError) as e:
            raise HTTPException(status_code=503, detail=str(e))


@router.post("/repos/index", response_model=IndexResponse)
def index_repo(body: IndexRequest):
    try:
        snap = resolve_source(
            git_url=body.git_url, local_path=body.local_path, sha=body.sha
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        files = iter_python_files(snap.workdir)
        chunks = chunk_workdir(snap.workdir, files)
        naive_total = 0
        for f in files:
            try:
                naive_total += len(naive_chunk(f.read_text(errors="replace")))
            except OSError:
                continue
        tests = sum(1 for c in chunks if c.is_test)
        persisted = False
        if body.persist:
            _persist(snap.repo_id, snap.source, snap.sha, chunks)
            persisted = True
        return IndexResponse(
            repo_id=snap.repo_id,
            sha=snap.sha,
            source=snap.source,
            persisted=persisted,
            chunks=[ChunkOut(**c.__dict__) for c in chunks],
            stats=IndexStats(
                files=len(files),
                functions=len(chunks),
                tests=tests,
                naive_chunks=naive_total,
            ),
        )
    finally:
        snap.dispose()
