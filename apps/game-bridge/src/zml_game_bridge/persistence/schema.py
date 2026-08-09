from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 14

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
-- Segments: runtime setup snapshots
-- =========================
CREATE TABLE IF NOT EXISTS run_segments (
    segment_id          TEXT PRIMARY KEY,
    run_id              INTEGER NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,

    segment_index       INTEGER NOT NULL,
    status              TEXT    NOT NULL DEFAULT 'active',
    started_ts_ms       INTEGER NOT NULL,
    ended_ts_ms         INTEGER,
    setup_hash          TEXT    NOT NULL,
    setup_snapshot_json TEXT    NOT NULL,
    notes               TEXT,

    created_ts_ms       INTEGER NOT NULL,
    updated_ts_ms       INTEGER NOT NULL,

    CHECK (status IN ('active', 'ended')),
    UNIQUE (run_id, segment_index)
);

CREATE INDEX IF NOT EXISTS idx_run_segments_run_id ON run_segments(run_id);
CREATE INDEX IF NOT EXISTS idx_run_segments_run_id_index ON run_segments(run_id, segment_index);
CREATE INDEX IF NOT EXISTS idx_run_segments_status ON run_segments(status);

CREATE TABLE IF NOT EXISTS events (
    event_id        INTEGER PRIMARY KEY,
    created_ts_ms   INTEGER NOT NULL,
    event_type      TEXT    NOT NULL,
    payload_json    TEXT    NOT NULL,
    run_id          INTEGER REFERENCES runs(run_id) ON DELETE CASCADE,
    segment_id      TEXT,

    -- Optional debug / query helpers
    event_dt        TEXT,
    raw             TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_created_ts_ms ON events(created_ts_ms);
CREATE INDEX IF NOT EXISTS idx_events_event_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_run_id_event_id ON events(run_id, event_id);
CREATE INDEX IF NOT EXISTS idx_events_segment_id_event_id ON events(segment_id, event_id);

CREATE TABLE IF NOT EXISTS mining_drops (
    drop_id                 TEXT PRIMARY KEY,
    drop_event_id           INTEGER NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,
    run_id                  INTEGER REFERENCES runs(run_id) ON DELETE SET NULL,
    segment_id              TEXT REFERENCES run_segments(segment_id) ON DELETE SET NULL,
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
    total_tt_cost_mpec      INTEGER NOT NULL,
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
CREATE INDEX IF NOT EXISTS idx_mining_drops_run_id ON mining_drops(run_id, observed_ts_ms);
CREATE INDEX IF NOT EXISTS idx_mining_drops_segment_id ON mining_drops(segment_id, observed_ts_ms);

CREATE TABLE IF NOT EXISTS mining_claims (
    claim_id                TEXT PRIMARY KEY,
    created_event_id        INTEGER NOT NULL REFERENCES events(event_id) ON DELETE CASCADE,

    hit_id                  TEXT,
    drop_id                 TEXT,
    run_id                  INTEGER REFERENCES runs(run_id) ON DELETE SET NULL,
    segment_id              TEXT REFERENCES run_segments(segment_id) ON DELETE SET NULL,
    observed_ts_ms          INTEGER NOT NULL,

    planet_name             TEXT,
    x                       INTEGER,
    y                       INTEGER,
    z                       INTEGER,
    search_radius_m         REAL,

    resource_name           TEXT,
    mining_type             TEXT,
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
    ignored_event_id        INTEGER REFERENCES events(event_id) ON DELETE SET NULL,
    ignored_ts_ms           INTEGER,
    ignored_reason          TEXT,
    expired_event_id        INTEGER REFERENCES events(event_id) ON DELETE SET NULL,
    expired_ts_ms           INTEGER,

    CHECK (status IN ('active', 'depleted'))
);

CREATE INDEX IF NOT EXISTS idx_mining_claims_status ON mining_claims(status);
CREATE INDEX IF NOT EXISTS idx_mining_claims_observed_ts_ms ON mining_claims(observed_ts_ms);
CREATE INDEX IF NOT EXISTS idx_mining_claims_expires ON mining_claims(expected_expires_ts_ms);
CREATE INDEX IF NOT EXISTS idx_mining_claims_ignored ON mining_claims(ignored_event_id);
CREATE INDEX IF NOT EXISTS idx_mining_claims_expired ON mining_claims(expired_event_id);

CREATE TABLE IF NOT EXISTS mining_loot_items (
    event_id                INTEGER PRIMARY KEY REFERENCES events(event_id) ON DELETE CASCADE,
    created_ts_ms           INTEGER NOT NULL,
    event_dt                TEXT,
    run_id                  INTEGER REFERENCES runs(run_id) ON DELETE SET NULL,

    item_name               TEXT NOT NULL,
    qty                     INTEGER NOT NULL,
    value_mpec              INTEGER NOT NULL,
    extraction_cost_mpec    INTEGER,
    raw                     TEXT
);

CREATE INDEX IF NOT EXISTS idx_mining_loot_run_id ON mining_loot_items(run_id, created_ts_ms);
CREATE INDEX IF NOT EXISTS idx_mining_loot_item_name ON mining_loot_items(item_name);

CREATE TABLE IF NOT EXISTS mining_loot_recent (
    loot_id                 INTEGER PRIMARY KEY,
    created_ts_ms           INTEGER NOT NULL,
    event_dt                TEXT,
    run_id                  INTEGER REFERENCES runs(run_id) ON DELETE SET NULL,
    segment_id              TEXT REFERENCES run_segments(segment_id) ON DELETE SET NULL,

    item_name               TEXT NOT NULL,
    qty                     INTEGER NOT NULL,
    value_mpec              INTEGER NOT NULL,
    extraction_cost_mpec    INTEGER,
    raw                     TEXT
);

CREATE INDEX IF NOT EXISTS idx_mining_loot_recent_run_id
    ON mining_loot_recent(run_id, created_ts_ms);
CREATE INDEX IF NOT EXISTS idx_mining_loot_recent_segment_id
    ON mining_loot_recent(segment_id, created_ts_ms);
CREATE INDEX IF NOT EXISTS idx_mining_loot_recent_item_name
    ON mining_loot_recent(item_name);

CREATE TABLE IF NOT EXISTS run_item_totals (
    run_id                  INTEGER NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    item_name               TEXT NOT NULL,
    qty                     INTEGER NOT NULL DEFAULT 0,
    value_mpec              INTEGER NOT NULL DEFAULT 0,
    extraction_cost_mpec    INTEGER NOT NULL DEFAULT 0,
    event_count             INTEGER NOT NULL DEFAULT 0,
    first_seen_ts_ms        INTEGER NOT NULL,
    last_seen_ts_ms         INTEGER NOT NULL,

    PRIMARY KEY (run_id, item_name)
);

CREATE INDEX IF NOT EXISTS idx_run_item_totals_run_value
    ON run_item_totals(run_id, value_mpec);

CREATE TABLE IF NOT EXISTS segment_item_totals (
    segment_id              TEXT NOT NULL REFERENCES run_segments(segment_id) ON DELETE CASCADE,
    run_id                  INTEGER NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    item_name               TEXT NOT NULL,
    qty                     INTEGER NOT NULL DEFAULT 0,
    value_mpec              INTEGER NOT NULL DEFAULT 0,
    extraction_cost_mpec    INTEGER NOT NULL DEFAULT 0,
    event_count             INTEGER NOT NULL DEFAULT 0,
    first_seen_ts_ms        INTEGER NOT NULL,
    last_seen_ts_ms         INTEGER NOT NULL,

    PRIMARY KEY (segment_id, item_name)
);

CREATE INDEX IF NOT EXISTS idx_segment_item_totals_run_id
    ON segment_item_totals(run_id);

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
    cur = conn.execute("PRAGMA user_version")
    user_version = int(cur.fetchone()[0])
    if user_version < 7:
        _archive_legacy_run_segments(conn)
    conn.executescript(SCHEMA_DDL)
    if user_version < 3 and not _column_exists(conn, "mining_drops", "drop_radius_m"):
        conn.execute("ALTER TABLE mining_drops ADD COLUMN drop_radius_m REAL NOT NULL DEFAULT 55.0")
    if user_version < 4 and not _column_exists(conn, "mining_drops", "expected_expires_ts_ms"):
        conn.execute("ALTER TABLE mining_drops ADD COLUMN expected_expires_ts_ms INTEGER")
    if user_version < 6 and not _column_exists(conn, "mining_drops", "finder_enhancer_decay_mpec"):
        conn.execute(
            "ALTER TABLE mining_drops ADD COLUMN finder_enhancer_decay_mpec INTEGER NOT NULL DEFAULT 0"
        )
    if user_version < 7:
        if not _column_exists(conn, "events", "segment_id"):
            conn.execute("ALTER TABLE events ADD COLUMN segment_id TEXT")
        if not _column_exists(conn, "mining_drops", "run_id"):
            conn.execute(
                "ALTER TABLE mining_drops ADD COLUMN run_id INTEGER REFERENCES runs(run_id) ON DELETE SET NULL"
            )
        if not _column_exists(conn, "mining_drops", "segment_id"):
            conn.execute(
                "ALTER TABLE mining_drops ADD COLUMN segment_id TEXT REFERENCES run_segments(segment_id) ON DELETE SET NULL"
            )
    if user_version < 8 and not _column_exists(conn, "mining_claims", "mining_type"):
        conn.execute("ALTER TABLE mining_claims ADD COLUMN mining_type TEXT")
    if user_version < 9:
        if not _column_exists(conn, "mining_claims", "run_id"):
            conn.execute(
                "ALTER TABLE mining_claims ADD COLUMN run_id INTEGER REFERENCES runs(run_id) ON DELETE SET NULL"
            )
        if not _column_exists(conn, "mining_claims", "segment_id"):
            conn.execute(
                "ALTER TABLE mining_claims ADD COLUMN segment_id TEXT REFERENCES run_segments(segment_id) ON DELETE SET NULL"
            )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_mining_claims_run_id ON mining_claims(run_id, observed_ts_ms)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_mining_claims_segment_id ON mining_claims(segment_id, observed_ts_ms)"
    )
    if user_version < 11:
        if not _column_exists(conn, "mining_claims", "ignored_event_id"):
            conn.execute(
                "ALTER TABLE mining_claims ADD COLUMN ignored_event_id INTEGER REFERENCES events(event_id) ON DELETE SET NULL"
            )
        if not _column_exists(conn, "mining_claims", "ignored_ts_ms"):
            conn.execute("ALTER TABLE mining_claims ADD COLUMN ignored_ts_ms INTEGER")
        if not _column_exists(conn, "mining_claims", "ignored_reason"):
            conn.execute("ALTER TABLE mining_claims ADD COLUMN ignored_reason TEXT")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_mining_claims_ignored ON mining_claims(ignored_event_id)"
    )
    if user_version < 12:
        if not _column_exists(conn, "mining_claims", "expired_event_id"):
            conn.execute(
                "ALTER TABLE mining_claims ADD COLUMN expired_event_id INTEGER REFERENCES events(event_id) ON DELETE SET NULL"
            )
        if not _column_exists(conn, "mining_claims", "expired_ts_ms"):
            conn.execute("ALTER TABLE mining_claims ADD COLUMN expired_ts_ms INTEGER")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_mining_claims_expired ON mining_claims(expired_event_id)"
    )
    if user_version < 14 and not _column_exists(
        conn, "mining_drops", "total_tt_cost_mpec"
    ):
        conn.execute(
            "ALTER TABLE mining_drops ADD COLUMN total_tt_cost_mpec INTEGER NOT NULL DEFAULT 0"
        )
        # Legacy drops only persisted the effective cost. Preserve that value as
        # the safest available TT fallback; all new drops store the exact split.
        conn.execute(
            "UPDATE mining_drops SET total_tt_cost_mpec = total_cost_mpec"
        )
    if user_version < SCHEMA_VERSION:
        conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    conn.commit()


def _archive_legacy_run_segments(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, "run_segments"):
        return
    if _column_exists(conn, "run_segments", "setup_snapshot_json"):
        return
    conn.execute("DROP INDEX IF EXISTS idx_run_segments_run_id")
    conn.execute("DROP INDEX IF EXISTS idx_run_segments_run_id_sort")
    conn.execute("ALTER TABLE run_segments RENAME TO run_segments_legacy_v6")


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    )
    return cur.fetchone() is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(str(row[1]) == column for row in cur.fetchall())
