from __future__ import annotations

import sqlite3
from pathlib import Path

from zml_game_bridge.events.envelope import EventEnvelope
from zml_game_bridge.storage.db_open import open_sqlite


class DbReader:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def open(self) -> None:
        self._conn = open_sqlite(self._db_path)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def read_after(self, after_event_id: int, *, limit: int = 200) -> list[EventEnvelope]:
        assert self._conn is not None, "DbReader not opened"
        cur = self._conn.execute(
            """
            SELECT event_id, created_ts_ms, event_dt, event_type, payload_json
            FROM events
            WHERE event_id > ?
            ORDER BY event_id ASC
            LIMIT ?
            """,
            (after_event_id, limit),
        )
        rows = cur.fetchall()
        return [
            EventEnvelope(
                event_id=int(r["event_id"]),
                created_ts_ms=int(r["created_ts_ms"]),
                event_dt=r["event_dt"],
                event_type=str(r["event_type"]),
                payload_json=str(r["payload_json"]),
            )
            for r in rows
        ]

    def read_latest(self, *, limit: int = 200) -> list[EventEnvelope]:
        assert self._conn is not None, "DbReader not opened"
        cur = self._conn.execute(
            """
            SELECT * FROM (
              SELECT event_id, created_ts_ms, event_dt, event_type, payload_json
              FROM events
              ORDER BY event_id DESC
              LIMIT ?
            )
            ORDER BY event_id ASC
            """,
            (limit,),
        )
        rows = cur.fetchall()
        return [
            EventEnvelope(
                event_id=int(r["event_id"]),
                created_ts_ms=int(r["created_ts_ms"]),
                event_dt=r["event_dt"],
                event_type=str(r["event_type"]),
                payload_json=str(r["payload_json"]),
            )
            for r in rows
        ]
