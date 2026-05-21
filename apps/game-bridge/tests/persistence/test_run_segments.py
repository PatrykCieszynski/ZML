from __future__ import annotations

import sqlite3
from pathlib import Path

from zml_game_bridge.domain.mining_events import RunSegmentEndedEvent, RunSegmentStartedEvent
from zml_game_bridge.persistence.event_writer import EventWriter
from zml_game_bridge.persistence.runs import RunSegmentProjector, RunSegmentStore, RunStore
from zml_game_bridge.persistence.schema import ensure_schema
from zml_game_bridge.persistence.sqlite import open_sqlite


def _open_test_db(tmp_path: Path) -> sqlite3.Connection:
    conn = open_sqlite(tmp_path / "run-segments.sqlite3")
    ensure_schema(conn)
    return conn


def test_run_segment_projector_stores_started_segment(tmp_path: Path) -> None:
    conn = _open_test_db(tmp_path)
    try:
        run_id = RunStore(conn).create_run(name="Run", notes=None, ts_ms=900)
        writer = EventWriter(conn, projector=RunSegmentProjector())

        writer.write(_started(run_id=run_id))

        rows = RunSegmentStore(conn).list_for_run(run_id)
        assert len(rows) == 1
        row = rows[0]
        assert row.segment_id == "segment-1"
        assert row.run_id == run_id
        assert row.segment_index == 1
        assert row.status == "active"
        assert row.started_ts_ms == 1_000
        assert row.ended_ts_ms is None
        assert row.setup_hash == "hash-1"
        assert row.setup_snapshot == {"finder": {"name": "Finder"}}
    finally:
        conn.close()


def test_run_segment_projector_marks_segment_ended(tmp_path: Path) -> None:
    conn = _open_test_db(tmp_path)
    try:
        run_id = RunStore(conn).create_run(name="Run", notes=None, ts_ms=900)
        writer = EventWriter(conn, projector=RunSegmentProjector())
        writer.write(_started(run_id=run_id))

        writer.write(
            RunSegmentEndedEvent(
                segment_id="segment-1",
                run_id=run_id,
                ended_ts_ms=2_000,
                reason="setup_changed",
            )
        )

        row = RunSegmentStore(conn).get("segment-1")
        assert row is not None
        assert row.status == "ended"
        assert row.ended_ts_ms == 2_000
    finally:
        conn.close()


def _started(*, run_id: int) -> RunSegmentStartedEvent:
    return RunSegmentStartedEvent(
        segment_id="segment-1",
        run_id=run_id,
        segment_index=1,
        started_ts_ms=1_000,
        setup_hash="hash-1",
        setup_snapshot={"finder": {"name": "Finder"}},
    )
