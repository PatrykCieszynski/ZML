# api/routes/ws_position.py
from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import cast

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from zml_game_bridge.api.schemas.position import PositionDto
from zml_game_bridge.runtime.runtime import AppRuntime

router = APIRouter(prefix="/ws", tags=["ws"])


@router.websocket("/position")
async def ws_position(ws: WebSocket) -> None:
    await ws.accept()

    runtime = cast(AppRuntime, ws.app.state.runtime)
    hub = runtime.position_hub  # property -> never None

    q, last = hub.subscribe()
    position_task = asyncio.create_task(q.get())
    disconnect_task = asyncio.create_task(_wait_for_disconnect(ws))
    shutdown_task = asyncio.create_task(runtime.shutdown_signal.wait())
    try:
        if last is not None:
            await ws.send_json(PositionDto.from_domain(last).model_dump())

        while True:
            done, _ = await asyncio.wait(
                (position_task, disconnect_task, shutdown_task),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if shutdown_task in done:
                await shutdown_task
                break
            if disconnect_task in done:
                await disconnect_task
                break

            pos = position_task.result()
            position_task = asyncio.create_task(q.get())
            await ws.send_json(PositionDto.from_domain(pos).model_dump())

    except WebSocketDisconnect:
        return
    except asyncio.CancelledError:
        raise
    finally:
        for task in (position_task, disconnect_task, shutdown_task):
            if not task.done():
                task.cancel()
        for task in (position_task, disconnect_task, shutdown_task):
            with suppress(asyncio.CancelledError, WebSocketDisconnect):
                await task
        hub.unsubscribe(q)


async def _wait_for_disconnect(ws: WebSocket) -> None:
    while True:
        message = await ws.receive()
        if message["type"] == "websocket.disconnect":
            return
