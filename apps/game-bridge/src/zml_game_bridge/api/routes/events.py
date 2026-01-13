import asyncio
import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import AsyncIterator

from fastapi import APIRouter, Depends, Query, Request
from starlette.responses import StreamingResponse

from zml_game_bridge.api.dto import EventEnvelopeDto
from zml_game_bridge.events.envelope import EventEnvelope
from zml_game_bridge.storage.db_reader import DbReader

router = APIRouter(prefix="/events", tags=["events"])

# TODO get path from config
local_app_data = os.getenv("LOCALAPPDATA") or str(Path.home())
db_path = Path(local_app_data) / "zabu-mining-log" / "db" / "zabu-mining-log.sqlite3"


def get_db_reader() -> Iterator[DbReader]:
    """
    FastAPI dependency:
    - opens DB
    - yields DbReader
    - always closes
    """
    db_reader = DbReader(db_path=db_path)
    db_reader.open()
    try:
        yield db_reader
    finally:
        db_reader.close()

def _to_dto(envelope: EventEnvelope) -> EventEnvelopeDto:
    return EventEnvelopeDto(
        event_id=envelope.event_id,
        created_ts_ms=envelope.created_ts_ms,
        event_dt=envelope.event_dt,
        event_type=envelope.event_type,
        payload=json.loads(envelope.payload_json),
    )


@router.get("/latest", response_model=list[EventEnvelopeDto])
def latest(
    limit: int = Query(default=200, ge=1, le=2000),
    db: DbReader = Depends(get_db_reader),
) -> list[EventEnvelopeDto]:
    rows = db.read_latest(limit=limit)
    return [_to_dto(r) for r in rows]


@router.get("/after/{after_event_id}", response_model=list[EventEnvelopeDto])
def after(
    after_event_id: int,
    limit: int = Query(default=200, ge=1, le=2000),
    db: DbReader = Depends(get_db_reader),
) -> list[EventEnvelopeDto]:
    rows = db.read_after(after_event_id, limit=limit)
    return [_to_dto(r) for r in rows]


@router.get("/stream")
async def events_stream(request: Request) -> StreamingResponse:
    runtime = request.app.state.runtime
    #TODO property/getter
    hub = runtime._sse_hub

    if hub is None:
        async def empty() -> AsyncIterator[str]:
            yield "event: error\ndata: {\"error\":\"sse hub not configured\"}\n\n"
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
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue

                dto = _to_dto(env)
                data = dto.model_dump_json(exclude={"event_id", "event_type"})  # pydantic v2

                # SSE format:
                # id: <...>
                # event: <...>
                # data: <json>
                yield f"id: {dto.event_id}\n"
                yield f"event: {dto.event_type}\n"
                yield f"data: {data}\n\n"
        finally:
            hub.unregister(client.client_id)

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",  # nginx: disable buffering
    }
    return StreamingResponse(gen(), media_type="text/event-stream", headers=headers)
