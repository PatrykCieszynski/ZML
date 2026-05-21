from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 6

SCHEMA_DDL = """
-- =========================
-- Runs: container, not a session
-- =========================
CREATE TABLE IF NOT EXISTS runs (
    run_id              INTEGER PRIMARY KEY,
    name                TEXT    NOT NULL,
    notes               TEXT,

    created_ts_ms       INTEGER NOT NULL,
    updated_ts_ms       INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active'
);

CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_updated_ts_ms ON runs(updated_ts_ms);


-- =========================
-- Segments: editable cost buckets
-- =========================
CREATE TABLE IF NOT EXISTS run_segments (
    segment_id          INTEGER PRIMARY KEY,
    run_id              INTEGER NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,

    -- e.g. "probes", "extract", "decay", "ammo", "manual_adjustment"
    kind                TEXT    NOT NULL,
    label               TEXT    NOT NULL,

    -- cost in integer mPEC
    qty                 INTEGER NOT NULL DEFAULT 1,
    unit_cost_mpec      INTEGER NOT NULL DEFAULT 0,

    -- generated avoids drift; SQLite supports STORED generated columns
    total_cost_mpec     INTEGER GENERATED ALWAYS AS (qty * unit_cost_mpec) STORED,

    is_active           INTEGER NOT NULL DEFAULT 1, -- 0/1

    -- optional metadata (tool name, amp, comment, OCR source, etc.)
    meta_json           TEXT    NOT NULL DEFAULT '{}',

    sort_key            INTEGER NOT NULL DEFAULT 0,

    created_ts_ms       INTEGER NOT NULL,
    updated_ts_ms       INTEGER NOT NULL,

    CHECK (is_active IN (0, 1)),
    CHECK (qty >= 0),
    CHECK (unit_cost_mpec >= 0)
);

CREATE INDEX IF NOT EXISTS idx_run_segments_run_id ON run_segments(run_id);
CREATE INDEX IF NOT EXISTS idx_run_segments_run_id_sort ON run_segments(run_id, sort_key);

CREATE TABLE IF NOT EXISTS events (
    event_id        INTEGER PRIMARY KEY,
    created_ts_ms   INTEGER NOT NULL,
    event_type      TEXT    NOT NULL,
    payload_json    TEXT    NOT NULL,
    run_id          INTEGER REFERENCES runs(run_id) ON DELETE CASCADE,

    -- Optional debug / query helpers
    event_dt        TEXT,
    raw             TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_created_ts_ms ON events(created_ts_ms);
CREATE INDEX IF NOT EXISTS idx_events_event_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_run_id_event_id ON events(run_id, event_id);

CREATE TABLE IF NOT EXISTS mining_drops (
    drop_id                 TEXT PRIMARY KEY,
    drop_event_id           INTEGER NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
    observed_ts_ms          INTEGER NOT NULL,

    planet_name             TEXT,
    x                       INTEGER,
    y                       INTEGER,
    z                       INTEGER,
    drop_radius_m           REAL NOT NULL DEFAULT 55.0,

    modes_mask              INTEGER,
    probes_per_drop         INTEGER,
    ammo_per_drop           INTEGER,

    ammo_cost_mpec          INTEGER NOT NULL,
    probes_cost_mpec        INTEGER NOT NULL,
    finder_decay_mpec       INTEGER NOT NULL,
    finder_enhancer_decay_mpec INTEGER NOT NULL DEFAULT 0,
    amp_decay_mpec          INTEGER NOT NULL,
    total_cost_mpec         INTEGER NOT NULL,

    result                  TEXT NOT NULL DEFAULT 'pending',
    result_event_id         INTEGER REFERENCES events(event_id) ON DELETE SET NULL,
    result_observed_ts_ms   INTEGER,

    hit_id                  TEXT,
    hit_event_id            INTEGER REFERENCES events(event_id) ON DELETE SET NULL,
    resource_name           TEXT,
    size_label              TEXT,
    size_index              INTEGER,
    expected_expires_ts_ms  INTEGER,
    range_m                 REAL,
    depth_m                 REAL,

    CHECK (result IN ('pending', 'hit', 'no_resources'))
);

CREATE INDEX IF NOT EXISTS idx_mining_drops_observed_ts_ms ON mining_drops(observed_ts_ms);
CREATE INDEX IF NOT EXISTS idx_mining_drops_result ON mining_drops(result);

CREATE TABLE IF NOT EXISTS mining_claims (
    claim_id                TEXT PRIMARY KEY,
    created_event_id        INTEGER NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,

    hit_id                  TEXT,
    drop_id                 TEXT,
    observed_ts_ms          INTEGER NOT NULL,

    planet_name             TEXT,
    x                       INTEGER,
    y                       INTEGER,
    z                       INTEGER,
    search_radius_m         REAL,

    resource_name           TEXT,
    size_label              TEXT,
    size_index              INTEGER,
    expected_expires_ts_ms  INTEGER,
    range_m                 REAL,
    depth_m                 REAL,

    status                  TEXT NOT NULL DEFAULT 'active',
    depleted_event_id       INTEGER REFERENCES events(event_id) ON DELETE SET NULL,
    depleted_event_dt       TEXT,
    depleted_planet_name    TEXT,
    depleted_x              INTEGER,
    depleted_y              INTEGER,
    depleted_z              INTEGER,
    depleted_distance_m     REAL,

    CHECK (status IN ('active', 'depleted'))
);

CREATE INDEX IF NOT EXISTS idx_mining_claims_status ON mining_claims(status);
CREATE INDEX IF NOT EXISTS idx_mining_claims_observed_ts_ms ON mining_claims(observed_ts_ms);
CREATE INDEX IF NOT EXISTS idx_mining_claims_expires ON mining_claims(expected_expires_ts_ms);

-- =========================
-- App state:
-- which run is currently "selected/active" after restart
-- =========================
CREATE TABLE IF NOT EXISTS app_state (
    key     TEXT PRIMARY KEY,
    value   TEXT NOT NULL
);

-- Example:
-- INSERT OR REPLACE INTO app_state(key, value) VALUES ('active_run_id', '123');
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_DDL)
    cur = conn.execute("PRAGMA user_version")
    user_version = int(cur.fetchone()[0])
    if user_version < 3 and not _column_exists(conn, "mining_drops", "drop_radius_m"):
        conn.execute("ALTER TABLE mining_drops ADD COLUMN drop_radius_m REAL NOT NULL DEFAULT 55.0")
    if user_version < 4 and not _column_exists(conn, "mining_drops", "expected_expires_ts_ms"):
        conn.execute("ALTER TABLE mining_drops ADD COLUMN expected_expires_ts_ms INTEGER")
    if user_version < 6 and not _column_exists(conn, "mining_drops", "finder_enhancer_decay_mpec"):
        conn.execute(
            "ALTER TABLE mining_drops ADD COLUMN finder_enhancer_decay_mpec INTEGER NOT NULL DEFAULT 0"
        )
    if user_version < SCHEMA_VERSION:
        conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    conn.commit()


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(str(row[1]) == column for row in cur.fetchall())
