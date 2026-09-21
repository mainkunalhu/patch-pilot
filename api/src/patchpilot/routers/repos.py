from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from patchpilot.indexer import chunk_workdir, naive_chunk
from patchpilot.ingest import iter_python_files, resolve_source

router = APIRouter()


class IndexRequest(BaseModel):
    git_url: str | None = Field(default=None)
    local_path: str | None = Field(default=None)
    sha: str | None = Field(default=None)


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
    chunks: list[ChunkOut]
    stats: IndexStats


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
        return IndexResponse(
            repo_id=snap.repo_id,
            sha=snap.sha,
            source=snap.source,
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
