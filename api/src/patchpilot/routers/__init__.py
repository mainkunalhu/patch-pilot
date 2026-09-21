from patchpilot.routers.health import router as health_router
from patchpilot.routers.patches import router as patches_router
from patchpilot.routers.query import router as query_router
from patchpilot.routers.repos import router as repos_router

__all__ = ["health_router", "patches_router", "query_router", "repos_router"]
