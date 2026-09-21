from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from patchpilot.agent.coder import CoderError, HunkContext
from patchpilot.agent.fixer import fix_loop
from patchpilot.retrieval.embed import EmbedError
from patchpilot.retrieval.service import retrieve_hunks
from patchpilot.retrieval.store import StoreError, connect, get_repo, get_run, save_run
from patchpilot.routers.patches import UsageOut
from patchpilot.runids import new_run_id

router = APIRouter()


class RunRequest(BaseModel):
    repo_id: str
    bug_text: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    max_attempts: int = Field(default=3, ge=1, le=3)
    timeout_s: int = Field(default=180, ge=30, le=600)


class RunResponse(BaseModel):
    run_id: str
    repo_id: str
    status: str
    diff: str | None
    test_log: str | None
    attempts: int
    flaky: bool
    usage: UsageOut


@router.post("/runs", response_model=RunResponse)
def create_run(body: RunRequest):
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
                "re-index with a local_path source to run fixes",
            )
        hunks = [
            HunkContext(path=h.chunk.path, name=h.chunk.name, content=h.chunk.content)
            for h in result.hunks
        ]
        try:
            fix = fix_loop(
                workdir,
                body.bug_text,
                hunks,
                max_attempts=body.max_attempts,
                timeout_s=body.timeout_s,
            )
        except CoderError as e:
            raise HTTPException(status_code=503, detail=str(e))

        run_id = new_run_id()
        try:
            save_run(
                conn,
                run_id=run_id,
                repo_id=body.repo_id,
                bug_text=body.bug_text,
                status=fix.status,
                diff=fix.diff,
                test_log=fix.test_log,
                prompt_tokens=fix.prompt_tokens,
                completion_tokens=fix.completion_tokens,
                tokens_per_sec=round(fix.tok_s, 1),
            )
        except StoreError as e:
            raise HTTPException(status_code=503, detail=str(e))

        return RunResponse(
            run_id=run_id,
            repo_id=body.repo_id,
            status=fix.status,
            diff=fix.diff,
            test_log=fix.test_log,
            attempts=fix.attempts,
            flaky=fix.flaky,
            usage=UsageOut(
                prompt_tokens=fix.prompt_tokens,
                completion_tokens=fix.completion_tokens,
                latency_s=0.0,
                tokens_per_sec=round(fix.tok_s, 1),
            ),
        )


@router.get("/runs/{run_id}", response_model=RunResponse)
def read_run(run_id: str):
    try:
        conn = connect()
    except StoreError as e:
        raise HTTPException(status_code=503, detail=str(e))
    with conn:
        try:
            row = get_run(conn, run_id)
        except StoreError as e:
            raise HTTPException(status_code=503, detail=str(e))
        if row is None:
            raise HTTPException(status_code=404, detail=f"unknown run {run_id}")
        return RunResponse(
            run_id=row.id,
            repo_id=row.repo_id or "",
            status=row.status,
            diff=row.diff,
            test_log=row.test_log,
            attempts=0,
            flaky=False,
            usage=UsageOut(
                prompt_tokens=row.prompt_tokens,
                completion_tokens=row.completion_tokens,
                latency_s=0.0,
                tokens_per_sec=row.tokens_per_sec or 0.0,
            ),
        )
