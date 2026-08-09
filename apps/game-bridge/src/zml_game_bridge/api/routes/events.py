from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Annotated

from fastapi import APIRouter, Query, Request
from starlette.responses import StreamingResponse

from zml_game_bridge.api.dependencies import EventReaderDep, RuntimeDep
from zml_game_bridge.api.schemas.events import EventEnvelopeDto
from zml_game_bridge.events.envelope import EventEnvelope

router = APIRouter(prefix="/events", tags=["events"])


def _to_dto(envelope: EventEnvelope) -> EventEnvelopeDto:
    return EventEnvelopeDto(
        event_id=envelope.event_id,
        created_ts_ms=envelope.created_ts_ms,
        event_dt=envelope.event_dt,
        event_type=envelope.event_type,
        payload=json.loads(envelope.payload_json),
    )


EventLimit = Annotated[int, Query(ge=1, le=2000)]


@router.get("/latest", response_model=list[EventEnvelopeDto])
def latest(
    db: EventReaderDep,
    limit: EventLimit = 200,
) -> list[EventEnvelopeDto]:
    rows = db.read_latest(limit=limit)
    return [_to_dto(r) for r in rows]


@router.get("/after/{after_event_id}", response_model=list[EventEnvelopeDto])
def after(
    after_event_id: int,
    db: EventReaderDep,
    limit: EventLimit = 200,
) -> list[EventEnvelopeDto]:
    rows = db.read_after(after_event_id, limit=limit)
    return [_to_dto(r) for r in rows]


@router.get("/stream")
async def events_stream(request: Request, runtime: RuntimeDep) -> StreamingResponse:
    hub = runtime.sse_hub

    if hub is None:

        async def empty() -> AsyncIterator[str]:
            yield 'event: error\ndata: {"error":"sse hub not configured"}\n\n'

        return StreamingResponse(empty(), media_type="text/event-stream")

    client = hub.register()

    async def gen() -> AsyncIterator[str]:
        event_task = asyncio.create_task(client.queue.get())
        shutdown_task = asyncio.create_task(runtime.shutdown_signal.wait())
        try:
            yield ": connected\n\n"

            while True:
                done, _ = await asyncio.wait(
                    (event_task, shutdown_task),
                    timeout=15.0,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if shutdown_task in done:
                    await shutdown_task
                    break
                if event_task not in done:
                    yield ": keep-alive\n\n"
                    continue

                env: EventEnvelope = event_task.result()
                event_task = asyncio.create_task(client.queue.get())
                dto = _to_dto(env)
                data = dto.model_dump_json(exclude={"event_id", "event_type"})

                # SSE format:
                # id: <...>
                # event: <...>
                # data: <json>
                if dto.event_id > 0:
                    yield f"id: {dto.event_id}\n"
                yield f"event: {dto.event_type}\n"
                yield f"data: {data}\n\n"
        finally:
            for task in (event_task, shutdown_task):
                if not task.done():
                    task.cancel()
            for task in (event_task, shutdown_task):
                with suppress(asyncio.CancelledError):
                    await task
            hub.unregister(client.client_id)

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(gen(), media_type="text/event-stream", headers=headers)
