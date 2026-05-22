from __future__ import annotations

import sqlite3
from pathlib import Path

from zml_game_bridge.api.routes.runs import (
    active_run,
    list_runs,
    resume_run,
    start_run,
    stop_run,
    update_run,
)
from zml_game_bridge.api.schemas.runs import (
    StartRunRequestDto,
    StopRunRequestDto,
    UpdateRunRequestDto,
)
from zml_game_bridge.persistence.schema import ensure_schema
from zml_game_bridge.persistence.sqlite import open_sqlite


def _open_test_db(tmp_path: Path) -> sqlite3.Connection:
    conn = open_sqlite(tmp_path / "runs.sqlite3")
    ensure_schema(conn)
    return conn


def test_start_stop_run_roundtrip(tmp_path: Path) -> None:
    conn = _open_test_db(tmp_path)
    try:
        started = start_run(StartRunRequestDto(name=" Test run "), conn)

        assert started.name == "Test run"
        assert started.status == "running"

        active = active_run(conn)
        assert active is not None
        assert active.run_id == started.run_id

        stopped = stop_run(StopRunRequestDto(), conn)

        assert stopped.run_id == started.run_id
        assert stopped.status == "stopped"
        assert active_run(conn) is None
    finally:
        conn.close()


def test_list_and_resume_run(tmp_path: Path) -> None:
    conn = _open_test_db(tmp_path)
    try:
        first = start_run(StartRunRequestDto(name="First"), conn)
        stopped = stop_run(StopRunRequestDto(), conn)
        second = start_run(StartRunRequestDto(name="Second"), conn)

        rows = list_runs(conn)
        assert [row.run_id for row in rows] == [second.run_id, stopped.run_id]

        resumed = resume_run(first.run_id, conn)

        assert resumed.run_id == first.run_id
        assert resumed.status == "running"
        active = active_run(conn)
        assert active is not None
        assert active.run_id == first.run_id
    finally:
        conn.close()


def test_update_run_name(tmp_path: Path) -> None:
    conn = _open_test_db(tmp_path)
    try:
        started = start_run(StartRunRequestDto(name="Old name", notes="keep"), conn)

        updated = update_run(started.run_id, UpdateRunRequestDto(name=" New name "), conn)

        assert updated.run_id == started.run_id
        assert updated.name == "New name"
        assert updated.notes == "keep"
    finally:
        conn.close()
