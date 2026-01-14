from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import asdict, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

from zml_game_bridge.events.base import EventBase
from zml_game_bridge.events.envelope import EventEnvelope
from zml_game_bridge.storage.sqlite import open_sqlite


class EventStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def open(self) -> None:
        self._conn = open_sqlite(self._db_path)

    def close(self) -> None:
        conn = self._conn
        if conn is not None:
            conn.close()
            self._conn = None

    def append(self, event: EventBase) -> EventEnvelope:
        """
        Persist event and return envelope.

        Assumption:
        - DB schema was already ensured elsewhere (runtime bootstrap).
        """
        conn = self._conn
        if conn is None:
            raise RuntimeError("EventStore not opened")

        event_type = type(event).__name__
        payload = _serialize_payload(event)

        created_ts_ms = time.time_ns() // 1_000_000
        payload_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

        raw = getattr(event, "raw", None)

        event_dt_obj = getattr(event, "event_dt", None)
        event_dt = event_dt_obj.isoformat() if isinstance(event_dt_obj, datetime) else None

        # Transaction: commit/rollback handled automatically.
        with conn:
            cur = conn.execute(
                """
                INSERT INTO events (created_ts_ms, event_type, payload_json, event_dt, raw)
                VALUES (?, ?, ?, ?, ?)
                """,
                (created_ts_ms, event_type, payload_json, event_dt, raw),
            )

        rowid = cur.lastrowid
        if rowid is None:
            raise RuntimeError("Failed to retrieve lastrowid after insert")

        return EventEnvelope(
            event_id=int(rowid),
            created_ts_ms=created_ts_ms,
            event_dt=event_dt,
            event_type=event_type,
            payload_json=payload_json,
        )


def _serialize_payload(event: EventBase) -> dict[str, Any]:
    if is_dataclass(event):
        payload = asdict(event)
        payload.pop("event_dt", None)
        payload.pop("channel_type", None)
        payload.pop("channel_token", None)
        payload.pop("raw", None)
    else:
        payload = dict(getattr(event, "__dict__", {}))
    return _to_jsonable(payload)


def _to_jsonable(obj: Any) -> Any:
    if obj is None:
        return None

    if isinstance(obj, (str, int, float, bool)):
        return obj

    if isinstance(obj, datetime):
        return obj.isoformat()

    if isinstance(obj, Decimal):
        return str(obj)

    if isinstance(obj, Enum):
        return obj.value

    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}

    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]

    return str(obj)
