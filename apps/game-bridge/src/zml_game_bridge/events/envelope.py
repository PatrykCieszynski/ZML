from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    event_id: int
    created_ts_ms: int
    event_dt: str | None
    event_type: str
    payload_json: str
