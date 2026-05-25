from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

WorkerStateDto = Literal["running", "degraded", "crashed", "stopped"]


class WorkerHealthDto(BaseModel):
    state: WorkerStateDto
    enabled: bool
    last_error: str | None
    last_seen_ts_ms: int


class HealthDto(BaseModel):
    status: WorkerStateDto
    workers: dict[str, WorkerHealthDto]
