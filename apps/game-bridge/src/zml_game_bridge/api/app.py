from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from zml_game_bridge.api.channels.position_hub import PositionHub
from zml_game_bridge.api.channels.sse_hub import SseHub
from zml_game_bridge.api.routes import register_routes
from zml_game_bridge.runtime.bootstrap import build_runtime_components, build_worker_supervisor
from zml_game_bridge.runtime.runtime import AppRuntime
from zml_game_bridge.settings import Settings

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = Settings()
    logger.info(
        "api_started host=%s port=%s db_path=%s chat_log_path=%s",
        settings.host,
        settings.port,
        settings.db_path,
        settings.chat_log_path,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        loop = asyncio.get_running_loop()
        sse_hub = SseHub(loop)
        position_hub = PositionHub(loop)
        supervisor = build_worker_supervisor(settings)
        runtime = AppRuntime(
            settings=settings,
            components=build_runtime_components(settings, supervisor=supervisor),
            supervisor=supervisor,
            sse_hub=sse_hub,
            position_hub=position_hub,
        )

        app.state.runtime = runtime
        runtime.start()
        try:
            yield
        finally:
            runtime.stop()

    app = FastAPI(title="Z Mining Log Game Bridge", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    register_routes(app)
    return app
