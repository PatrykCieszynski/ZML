from __future__ import annotations

import sqlite3
from pathlib import Path

from zml_game_bridge.api.dto import StartRunRequestDto, StopRunRequestDto
from zml_game_bridge.api.routes.runs import active_run, start_run, stop_run
from zml_game_bridge.storage.db_schema import ensure_schema
from zml_game_bridge.storage.sqlite import open_sqlite


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
