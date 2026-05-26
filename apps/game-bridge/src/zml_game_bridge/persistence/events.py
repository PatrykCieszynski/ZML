from __future__ import annotations

import sqlite3
import time
from datetime import datetime
from pathlib import Path

from zml_game_bridge.events.base import EventBase
from zml_game_bridge.events.envelope import EventEnvelope
from zml_game_bridge.events.serialization import event_payload_json
from zml_game_bridge.persistence.sqlite import open_read_connection


class EventStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn: sqlite3.Connection | None = conn

    def append(self, event: EventBase) -> EventEnvelope:
        """
        Persist event and return envelope.

        Assumption:
        - DB schema was already ensured elsewhere.
        - Transaction ownership belongs to the caller.
        """
        conn = self._conn
        if conn is None:
            raise RuntimeError("EventStore not opened")

        event_type = type(event).__name__
        created_ts_ms = time.time_ns() // 1_000_000
        payload_json = event_payload_json(event)

        raw = getattr(event, "raw", None)
        run_id = getattr(event, "run_id", None)
        segment_id = getattr(event, "segment_id", None)

        event_dt_obj = getattr(event, "event_dt", None)
        event_dt = event_dt_obj.isoformat() if isinstance(event_dt_obj, datetime) else None

        cur = conn.execute(
            """
            INSERT INTO events (created_ts_ms, event_type, payload_json, run_id, segment_id, event_dt, raw)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (created_ts_ms, event_type, payload_json, run_id, segment_id, event_dt, raw),
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


class EventReader:
    def __init__(self, db_path: Path, *, check_same_thread: bool = True) -> None:
        self._db_path = db_path
        self._check_same_thread = check_same_thread
        self._conn: sqlite3.Connection | None = None

    def open(self) -> None:
        self._conn = open_read_connection(
            self._db_path,
            check_same_thread=self._check_same_thread,
        )

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def read_after(self, after_event_id: int, *, limit: int = 200) -> list[EventEnvelope]:
        assert self._conn is not None, "EventReader not opened"
        cur = self._conn.execute(
            """
            SELECT event_id, created_ts_ms, event_dt, event_type, payload_json
            FROM events
            WHERE event_id > ?
            ORDER BY event_id
            LIMIT ?
            """,
            (after_event_id, limit),
        )
        return [_row_to_event_envelope(row) for row in cur.fetchall()]

    def read_latest(self, *, limit: int = 200) -> list[EventEnvelope]:
        assert self._conn is not None, "EventReader not opened"
        cur = self._conn.execute(
            """
            SELECT *
            FROM (SELECT event_id, created_ts_ms, event_dt, event_type, payload_json
                  FROM events
                  ORDER BY event_id DESC
                  LIMIT ?)
            ORDER BY event_id
            """,
            (limit,),
        )
        return [_row_to_event_envelope(row) for row in cur.fetchall()]


def _row_to_event_envelope(row: sqlite3.Row) -> EventEnvelope:
    return EventEnvelope(
        event_id=int(row["event_id"]),
        created_ts_ms=int(row["created_ts_ms"]),
        event_dt=row["event_dt"],
        event_type=str(row["event_type"]),
        payload_json=str(row["payload_json"]),
    )
