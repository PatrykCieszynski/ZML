from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterator
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request

from zml_game_bridge.api.dto import RunDto, StartRunRequestDto, StopRunRequestDto
from zml_game_bridge.app.runtime import AppRuntime
from zml_game_bridge.services.run_state import RunState
from zml_game_bridge.storage.db_schema import ensure_schema
from zml_game_bridge.storage.run_store import RunStore
from zml_game_bridge.storage.sqlite import open_sqlite

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])


def get_run_conn(request: Request) -> Iterator[sqlite3.Connection]:
    runtime = cast(AppRuntime, request.app.state.runtime)
    conn = open_sqlite(runtime.db_path)
    ensure_schema(conn)
    try:
        yield conn
    finally:
        conn.close()


RunConn = Annotated[sqlite3.Connection, Depends(get_run_conn)]


@router.post("/start", response_model=RunDto)
def start_run(request: StartRunRequestDto, conn: RunConn) -> RunDto:
    name = request.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Run name must not be empty")

    state = RunState(conn)
    with conn:
        run_id = state.create_run(name=name, notes=request.notes, activate=True)
        row = RunStore(conn).get_run(run_id)

    if row is None:
        raise HTTPException(status_code=500, detail="Run was not created")
    return RunDto.from_row(row)


@router.post("/stop", response_model=RunDto)
def stop_run(request: StopRunRequestDto, conn: RunConn) -> RunDto:
    store = RunStore(conn)
    state = RunState(conn)

    run_id = request.run_id if request.run_id is not None else state.try_get_active_run_id()
    if run_id is None:
        raise HTTPException(status_code=404, detail="No active run")

    row = store.get_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    with conn:
        store.set_run_status(run_id, status="stopped", ts_ms=_now_ms())
        state.clear_active_run(run_id)
        stopped = store.get_run(run_id)

    if stopped is None:
        raise HTTPException(status_code=500, detail="Run disappeared while stopping")
    return RunDto.from_row(stopped)


@router.get("/active", response_model=RunDto | None)
def active_run(conn: RunConn) -> RunDto | None:
    state = RunState(conn)
    run_id = state.try_get_active_run_id()
    if run_id is None:
        return None

    row = RunStore(conn).get_run(run_id)
    return RunDto.from_row(row) if row is not None else None


def _now_ms() -> int:
    return time.time_ns() // 1_000_000
