from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from zml_backend.application.position.model import PositionSnapshot


class PositionDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ts_ms: int
    planet_name: str | None
    x: int
    y: int
    z: int | None

    @classmethod
    def from_domain(cls, pos: PositionSnapshot) -> PositionDto:
        return cls(
            ts_ms=pos.observed_ts_ms,
            planet_name=pos.position.planet_name,
            x=pos.position.x,
            y=pos.position.y,
            z=pos.position.z,
        )
