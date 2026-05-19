from fastapi import FastAPI

from .events import router as events_router
from .health import router as health_router
from .mining import router as mining_router
from .runs import router as runs_router
from .ws_position import router as position_router


def register_routes(app: FastAPI) -> None:
    """Register all API routers on the app."""
    app.include_router(health_router)
    app.include_router(events_router)
    app.include_router(runs_router)
    app.include_router(mining_router)
    app.include_router(position_router)
