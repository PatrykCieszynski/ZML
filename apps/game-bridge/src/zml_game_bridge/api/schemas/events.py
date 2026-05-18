from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class EventEnvelopeDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    event_id: int
    created_ts_ms: int
    event_dt: str | None
    event_type: str
    payload: dict[str, Any]
