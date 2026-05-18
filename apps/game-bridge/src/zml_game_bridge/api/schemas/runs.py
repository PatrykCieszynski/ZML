from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from zml_game_bridge.persistence.runs import RunRow


class RunDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: int
    name: str
    status: str
    notes: str | None = None
    created_ts_ms: int
    updated_ts_ms: int

    @classmethod
    def from_row(cls, row: RunRow) -> RunDto:
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
