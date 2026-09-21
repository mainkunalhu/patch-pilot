from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from patchpilot.agent.coder import CoderError, HunkContext, propose_patch
from patchpilot.retrieval.embed import EmbedError
from patchpilot.retrieval.service import retrieve_hunks
from patchpilot.retrieval.store import StoreError, connect, get_repo, save_run
from patchpilot.runids import new_run_id

router = APIRouter()


class PatchRequest(BaseModel):
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


class UsageOut(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    latency_s: float
    tokens_per_sec: float


class PatchResponse(BaseModel):
    run_id: str
    repo_id: str
    valid: bool
    diff: str | None
    validation_error: str | None
    attempts: int
    hunks_used: list[HunkOut]
    usage: UsageOut


@router.post("/patch", response_model=PatchResponse)
def create_patch(body: PatchRequest):
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
        repo = get_repo(conn, body.repo_id)
        if repo is None:
            raise HTTPException(status_code=404, detail=f"unknown repo {body.repo_id}")
        workdir = Path(repo.source)
        if not workdir.is_dir():
            raise HTTPException(
                status_code=422,
                detail=f"repo files not available locally at {repo.source}; "
                "re-index with a local_path source to propose patches",
            )
        hunks = [
            HunkContext(
                path=h.chunk.path,
                name=h.chunk.name,
                content=h.chunk.content,
                start_line=h.chunk.start_line,
                end_line=h.chunk.end_line,
            )
            for h in result.hunks
        ]
        try:
            proposal = propose_patch(workdir, body.bug_text, hunks)
        except CoderError as e:
            raise HTTPException(status_code=503, detail=str(e))

        run_id = new_run_id()
        v = proposal.validation
        res = proposal.result
        try:
            save_run(
                conn,
                run_id=run_id,
                repo_id=body.repo_id,
                bug_text=body.bug_text,
                status="patch_proposed" if v.ok else "patch_invalid",
                diff=v.diff or None,
                prompt_tokens=res.prompt_tokens,
                completion_tokens=res.completion_tokens,
                tokens_per_sec=round(res.tok_s, 1),
            )
        except StoreError as e:
            raise HTTPException(status_code=503, detail=str(e))

        return PatchResponse(
            run_id=run_id,
            repo_id=body.repo_id,
            valid=v.ok,
            diff=v.diff or None,
            validation_error=None if v.ok else v.error,
            attempts=proposal.attempts,
            hunks_used=[
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
            usage=UsageOut(
                prompt_tokens=res.prompt_tokens,
                completion_tokens=res.completion_tokens,
                latency_s=round(res.latency_s, 2),
                tokens_per_sec=round(res.tok_s, 1),
            ),
        )
