from fastapi import FastAPI

from .health import router as health_router
from .events import router as events_router


def register_routes(app: FastAPI) -> None:
    """Register all API routers on the app."""
    app.include_router(health_router)
    app.include_router(events_router)
