from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from patchpilot.config import settings
from patchpilot.routers import (
    health_router,
    patches_router,
    query_router,
    repos_router,
    runs_router,
)


def create_app() -> FastAPI:
    app = FastAPI(title="PatchPilot API", version="0.1.0")
    # Browser UI (bun dev on :3000) calls this API directly.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(repos_router)
    app.include_router(query_router)
    app.include_router(patches_router)
    app.include_router(runs_router)
    return app


app = create_app()


@app.get("/")
def root():
    return {"name": "PatchPilot API", "env": settings.env}
