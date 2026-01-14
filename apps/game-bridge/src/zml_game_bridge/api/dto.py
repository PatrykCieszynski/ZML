from typing import Literal
from pydantic import BaseModel, ConfigDict
from typing_extensions import Any

from zml_game_bridge.inputs.ocr.model import OcrPosition


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
    z: int

    @classmethod
    def from_domain(cls, pos: OcrPosition) -> "PositionDto":
        return cls(
            ts_ms=pos.ts_ms,
            planet_name=pos.position.planet_name,
            x=pos.position.x,
            y=pos.position.y,
            z=pos.position.z,
        )