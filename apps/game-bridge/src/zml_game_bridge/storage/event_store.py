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
from zml_game_bridge.storage.db_open import open_sqlite

_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS events (
    event_id        INTEGER PRIMARY KEY,
    created_ts_ms   INTEGER NOT NULL,
    event_type      TEXT    NOT NULL,
    payload_json    TEXT    NOT NULL,

    -- Optional debug / query helpers
    event_dt        TEXT,
    raw             TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_created_ts_ms ON events(created_ts_ms);
CREATE INDEX IF NOT EXISTS idx_events_event_type ON events(event_type);
"""


class EventStore:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def open(self) -> None:
        """Open connection and ensure schema exists."""

        # Ensure parent dir exists
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        # Open sqlite connection
        self._conn = open_sqlite(db_path=self._db_path)

        # Recommended pragmas (optional): WAL, foreign_keys, busy_timeout
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=5000")

        # Ensure schema + set PRAGMA user_version=1
        self.init_schema()

    def close(self) -> None:
        """Close connection if open."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def init_schema(self) -> None:
        """Create tables/indexes if missing."""
        assert self._conn is not None, "EventStore not opened"
        self._conn.executescript(_SCHEMA_DDL)
        if self._conn.execute("PRAGMA user_version").fetchone()[0] == 0:
            self._conn.execute("PRAGMA user_version=1")
        self._conn.commit()


    def append(self, event: EventBase) -> EventEnvelope:
        """
        Persist event and return event_id.

        Policy:
        - If DB write fails -> raise (caller decides to drop/panic).
        """
        # TODO batch commits
        assert self._conn is not None, "EventStore not opened"

        event_type = type(event).__name__
        payload = _serialize_payload(event)

        created_ts_ms = time.time_ns() // 1_000_000
        payload_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

        raw = getattr(event, "raw", None)
        event_dt = getattr(event, "event_dt", None)
        event_dt = event_dt.isoformat() if event_dt and isinstance(event_dt, datetime) else None

        cursor = self._conn.cursor().execute(
            """
            INSERT INTO events (created_ts_ms, event_type, payload_json, event_dt, raw)
            VALUES (?, ?, ?, ?, ?)
            """,
            (created_ts_ms, event_type, payload_json, event_dt, raw),
        )
        rowid = cursor.lastrowid
        self._conn.commit()
        if rowid is None:
            raise RuntimeError("Failed to retrieve lastrowid after insert")
        return _create_envelope(rowid,created_ts_ms, event_dt, event_type, payload_json)


def _serialize_payload(event: EventBase) -> dict[str, Any]:
    """
    Convert event dataclass to JSON-friendly dict.
    """
    if is_dataclass(event):
        payload = asdict(event)
        payload.pop("event_dt", None)
        payload.pop("channel_type", None)
        payload.pop("channel_token", None)
        payload.pop("raw", None)
    else:
        # Fallback: try __dict__ (should not happen if all events are dataclasses)
        payload = dict(getattr(event, "__dict__", {}))

    return _to_jsonable(payload)


def _create_envelope(event_id: int, created_ts_ms: int, event_dt: str | None, event_type: str, payload_json: str) -> EventEnvelope:
    """Create event envelope dict."""
    envelope = EventEnvelope(
        event_id=event_id,
        created_ts_ms=created_ts_ms,
        event_dt=event_dt,
        event_type=event_type,
        payload_json=payload_json
    )
    return envelope


def _to_jsonable(obj: Any) -> Any:
    """Recursively convert objects to JSON-friendly types."""
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

    # Last resort: stable string representation
    return str(obj)
