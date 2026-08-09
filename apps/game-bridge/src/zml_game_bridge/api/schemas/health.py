from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

WorkerStateDto = Literal["running", "degraded", "crashed", "stopped"]
HealthDetailDto = str | int | float | bool | None


class WorkerHealthDto(BaseModel):
    state: WorkerStateDto
    enabled: bool
    last_error: str | None
    last_seen_ts_ms: int
    details: dict[str, HealthDetailDto] = Field(default_factory=dict)


class HealthDto(BaseModel):
    status: WorkerStateDto
    workers: dict[str, WorkerHealthDto]
