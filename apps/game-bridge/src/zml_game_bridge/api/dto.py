from typing import Literal
from pydantic import BaseModel, ConfigDict
from typing_extensions import Any


class EventEnvelopeDto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    event_id: int
    created_ts_ms: int
    event_dt: str | None
    event_type: str
    payload: dict[str, Any]