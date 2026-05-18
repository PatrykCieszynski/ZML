from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from zml_game_bridge.inputs.ocr.pipelines.position.model import OcrPosition
from zml_game_bridge.storage.run_store import RunRow


class EventEnvelopeDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    event_id: int
    created_ts_ms: int
    event_dt: str | None
    event_type: str
    payload: dict[str, Any]


class PositionDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ts_ms: int
    planet_name: str | None
    x: int
    y: int
    z: int | None

    @classmethod
    def from_domain(cls, pos: OcrPosition) -> "PositionDto":
        return cls(
            ts_ms=pos.ts_ms,
            planet_name=pos.position.planet_name,
            x=pos.position.x,
            y=pos.position.y,
            z=pos.position.z,
        )


class RunDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: int
    name: str
    status: str
    notes: str | None = None
    created_ts_ms: int
    updated_ts_ms: int

    @classmethod
    def from_row(cls, row: RunRow) -> "RunDto":
        return cls(
            run_id=row.run_id,
            name=row.name,
            status=row.status,
            notes=row.notes,
            created_ts_ms=row.created_ts_ms,
            updated_ts_ms=row.updated_ts_ms,
        )


class StartRunRequestDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    notes: str | None = None


class StopRunRequestDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: int | None = None
