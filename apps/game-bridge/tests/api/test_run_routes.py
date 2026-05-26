from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, cast

from zml_game_bridge.api.routes.runs import (
    active_run,
    delete_run,
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
from zml_game_bridge.runtime.db_commands import DbCommand
from zml_game_bridge.runtime.runtime_commands import RuntimeCommand


def _open_test_db(tmp_path: Path) -> sqlite3.Connection:
    conn = open_sqlite(tmp_path / "runs.sqlite3")
    ensure_schema(conn)
    return conn


class _RuntimeStub:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def execute_runtime_command[T](
        self,
        command: RuntimeCommand[T],
        *,
        timeout_s: float = 5.0,
    ) -> T:
        del timeout_s
        with self.conn:
            return cast(DbCommand[T], command).execute(self.conn)


def test_start_stop_run_roundtrip(tmp_path: Path) -> None:
    conn = _open_test_db(tmp_path)
    runtime: Any = _RuntimeStub(conn)
    try:
        started = start_run(StartRunRequestDto(name=" Test run "), runtime)

        assert started.name == "Test run"
        assert started.status == "running"

        active = active_run(conn)
        assert active is not None
        assert active.run_id == started.run_id

        stopped = stop_run(StopRunRequestDto(), runtime)

        assert stopped.run_id == started.run_id
        assert stopped.status == "stopped"
        assert active_run(conn) is None
    finally:
        conn.close()


def test_list_and_resume_run(tmp_path: Path) -> None:
    conn = _open_test_db(tmp_path)
    runtime: Any = _RuntimeStub(conn)
    try:
        first = start_run(StartRunRequestDto(name="First"), runtime)
        stopped = stop_run(StopRunRequestDto(), runtime)
        second = start_run(StartRunRequestDto(name="Second"), runtime)

        rows = list_runs(conn)
        assert [row.run_id for row in rows] == [second.run_id, stopped.run_id]

        resumed = resume_run(first.run_id, runtime)

        assert resumed.run_id == first.run_id
        assert resumed.status == "running"
        active = active_run(conn)
        assert active is not None
        assert active.run_id == first.run_id
    finally:
        conn.close()


def test_update_run_name(tmp_path: Path) -> None:
    conn = _open_test_db(tmp_path)
    runtime: Any = _RuntimeStub(conn)
    try:
        started = start_run(StartRunRequestDto(name="Old name", notes="keep"), runtime)

        updated = update_run(started.run_id, UpdateRunRequestDto(name=" New name "), runtime)

        assert updated.run_id == started.run_id
        assert updated.name == "New name"
        assert updated.notes == "keep"
    finally:
        conn.close()


def test_delete_run_marks_deleted_and_hides_from_default_list(tmp_path: Path) -> None:
    conn = _open_test_db(tmp_path)
    runtime: Any = _RuntimeStub(conn)
    try:
        first = start_run(StartRunRequestDto(name="First"), runtime)
        second = start_run(StartRunRequestDto(name="Second"), runtime)

        deleted = delete_run(first.run_id, runtime)

        assert deleted.run_id == first.run_id
        assert deleted.status == "deleted"
        assert [row.run_id for row in list_runs(conn)] == [second.run_id]
        assert {row.run_id for row in list_runs(conn, include_deleted=True)} == {
            first.run_id,
            second.run_id,
        }

        resumed = resume_run(second.run_id, runtime)

        assert resumed.run_id == second.run_id
        assert active_run(conn) is not None
    finally:
        conn.close()


def test_delete_active_run_clears_active_run(tmp_path: Path) -> None:
    conn = _open_test_db(tmp_path)
    runtime: Any = _RuntimeStub(conn)
    try:
        started = start_run(StartRunRequestDto(name="Active"), runtime)

        deleted = delete_run(started.run_id, runtime)

        assert deleted.status == "deleted"
        assert active_run(conn) is None
    finally:
        conn.close()
