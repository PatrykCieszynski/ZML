from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Iterator
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query, Request
from starlette.responses import StreamingResponse

from zml_game_bridge.api.schemas.events import EventEnvelopeDto
from zml_game_bridge.events.envelope import EventEnvelope
from zml_game_bridge.persistence.events import EventReader
from zml_game_bridge.runtime.runtime import AppRuntime

router = APIRouter(prefix="/events", tags=["events"])


def get_event_reader(request: Request) -> Iterator[EventReader]:
    """
    FastAPI dependency:
    - opens DB
    - yields EventReader
    - always closes
    """
    runtime = cast(AppRuntime, request.app.state.runtime)
    event_reader = EventReader(db_path=runtime.db_path, check_same_thread=False)
    event_reader.open()
    try:
        yield event_reader
    finally:
        event_reader.close()


def _to_dto(envelope: EventEnvelope) -> EventEnvelopeDto:
    return EventEnvelopeDto(
        event_id=envelope.event_id,
        created_ts_ms=envelope.created_ts_ms,
        event_dt=envelope.event_dt,
        event_type=envelope.event_type,
        payload=json.loads(envelope.payload_json),
    )


EventReaderDep = Annotated[EventReader, Depends(get_event_reader)]
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
async def events_stream(request: Request) -> StreamingResponse:
    runtime = cast(AppRuntime, request.app.state.runtime)
    hub = runtime.sse_hub

    if hub is None:

        async def empty() -> AsyncIterator[str]:
            yield 'event: error\ndata: {"error":"sse hub not configured"}\n\n'

        return StreamingResponse(empty(), media_type="text/event-stream")

    client = hub.register()

    async def gen() -> AsyncIterator[str]:
        try:
            yield ": connected\n\n"

            while True:
                if await request.is_disconnected():
                    break

                try:
                    env: EventEnvelope = await asyncio.wait_for(client.queue.get(), timeout=15.0)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue

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
            hub.unregister(client.client_id)

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(gen(), media_type="text/event-stream", headers=headers)
