import json
import os
from collections.abc import Iterator
from pathlib import Path

from fastapi import APIRouter, Depends, Query

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
