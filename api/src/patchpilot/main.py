from fastapi import FastAPI

from patchpilot.config import settings
from patchpilot.routers import health


def create_app() -> FastAPI:
    app = FastAPI(title="PatchPilot API", version="0.1.0")
    app.include_router(health.router)
    return app


app = create_app()


@app.get("/")
def root():
    return {"name": "PatchPilot API", "env": settings.env}
