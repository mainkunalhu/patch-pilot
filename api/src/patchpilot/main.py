from fastapi import FastAPI

from patchpilot.config import settings
from patchpilot.routers import (
    health_router,
    patches_router,
    query_router,
    repos_router,
)


def create_app() -> FastAPI:
    app = FastAPI(title="PatchPilot API", version="0.1.0")
    app.include_router(health_router)
    app.include_router(repos_router)
    app.include_router(query_router)
    app.include_router(patches_router)
    return app


app = create_app()


@app.get("/")
def root():
    return {"name": "PatchPilot API", "env": settings.env}
