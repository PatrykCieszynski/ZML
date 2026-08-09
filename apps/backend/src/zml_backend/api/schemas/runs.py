from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from zml_backend.persistence.runs import RunRow, RunSegmentRow


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


class RunSegmentDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segment_id: str
    run_id: int
    segment_index: int
    status: str
    started_ts_ms: int
    ended_ts_ms: int | None
    setup_hash: str
    setup_snapshot: dict[str, Any]
    notes: str | None = None
    created_ts_ms: int
    updated_ts_ms: int

    @classmethod
    def from_row(cls, row: RunSegmentRow) -> RunSegmentDto:
        return cls(
            segment_id=row.segment_id,
            run_id=row.run_id,
            segment_index=row.segment_index,
            status=row.status,
            started_ts_ms=row.started_ts_ms,
            ended_ts_ms=row.ended_ts_ms,
            setup_hash=row.setup_hash,
            setup_snapshot=dict(row.setup_snapshot),
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


class UpdateRunRequestDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    notes: str | None = None
