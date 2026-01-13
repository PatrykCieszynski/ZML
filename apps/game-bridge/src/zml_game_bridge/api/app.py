from __future__ import annotations

from contextlib import asynccontextmanager
from fastapi import FastAPI

from zml_game_bridge.api.routes import register_routes
from zml_game_bridge.app.runtime import AppRuntime
from zml_game_bridge.settings import Settings


def create_app() -> FastAPI:
    settings = Settings()
    print(f"Starting ZML Game Bridge with settings: {settings.chat_log_path}")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runtime = AppRuntime(db_path=settings.db_path, chat_log_path=settings.chat_log_path)
        app.state.runtime = runtime
        runtime.start()
        try:
            yield
        finally:
            runtime.stop()

    app = FastAPI(title="ZML Game Bridge", version="0.1.0", lifespan=lifespan)
    register_routes(app)
    return app
