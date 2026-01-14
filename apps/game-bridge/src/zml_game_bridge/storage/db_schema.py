from __future__ import annotations
import sqlite3

SCHEMA_VERSION = 1

SCHEMA_DDL = """
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


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_DDL)
    cur = conn.execute("PRAGMA user_version")
    user_version = int(cur.fetchone()[0])
    if user_version == 0:
        conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    conn.commit()