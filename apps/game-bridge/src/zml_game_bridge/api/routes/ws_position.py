# api/routes/ws_position.py
from __future__ import annotations

import asyncio
from typing import cast

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from zml_game_bridge.api.dto import PositionDto
from zml_game_bridge.app.runtime import AppRuntime

router = APIRouter(prefix="/ws", tags=["ws"])


@router.websocket("/position")
async def ws_position(ws: WebSocket) -> None:
    await ws.accept()

    runtime = cast(AppRuntime, ws.app.state.runtime)
    hub = runtime.position_hub  # property -> never None

    q, last = hub.subscribe()
    try:
        if last is not None:
            await ws.send_json(PositionDto.from_domain(last).model_dump())

        while True:
            pos = await q.get()
            await ws.send_json(PositionDto.from_domain(pos).model_dump())

    except WebSocketDisconnect:
        return
    except asyncio.CancelledError:
        raise
    finally:
        hub.unsubscribe(q)
