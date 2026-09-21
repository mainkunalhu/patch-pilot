from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from patchpilot.retrieval.embed import EmbedError
from patchpilot.retrieval.service import retrieve_hunks
from patchpilot.retrieval.store import StoreError, connect
from patchpilot.routers.patches import HunkOut

router = APIRouter()


class QueryRequest(BaseModel):
    repo_id: str
    bug_text: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


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
            result = retrieve_hunks(conn, body.repo_id, body.bug_text, body.top_k)
        except LookupError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except (StoreError, EmbedError) as e:
            raise HTTPException(status_code=503, detail=str(e))
        return QueryResponse(
            repo_id=body.repo_id,
            query=result.query,
            rewritten=result.rewritten,
            hunks=[
                HunkOut(
                    path=h.chunk.path,
                    lang=h.chunk.lang,
                    name=h.chunk.name,
                    content=h.chunk.content,
                    is_test=h.chunk.is_test,
                    start_line=h.chunk.start_line,
                    end_line=h.chunk.end_line,
                    score=h.score,
                    sources=h.sources,
                )
                for h in result.hunks
            ],
        )
