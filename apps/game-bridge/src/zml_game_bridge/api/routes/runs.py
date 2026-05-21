from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterator
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request

from zml_game_bridge.api.schemas.runs import (
    RunDto,
    RunSegmentDto,
    StartRunRequestDto,
    StopRunRequestDto,
)
from zml_game_bridge.persistence.runs import RunSegmentStore, RunStore
from zml_game_bridge.persistence.schema import ensure_schema
from zml_game_bridge.persistence.sqlite import open_sqlite
from zml_game_bridge.runs.state import RunState
from zml_game_bridge.runtime.runtime import AppRuntime

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])


def get_run_conn(request: Request) -> Iterator[sqlite3.Connection]:
    runtime = cast(AppRuntime, request.app.state.runtime)
    conn = open_sqlite(runtime.db_path, check_same_thread=False)
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
        ts_ms = _now_ms()
        store.set_run_status(run_id, status="stopped", ts_ms=ts_ms)
        RunSegmentStore(conn).end_active_for_run(run_id, ended_ts_ms=ts_ms, ts_ms=ts_ms)
        state.clear_active_run(run_id)
        stopped = store.get_run(run_id)

    if stopped is None:
        raise HTTPException(status_code=500, detail="Run disappeared while stopping")
    return RunDto.from_row(stopped)


@router.get("", response_model=list[RunDto])
def list_runs(conn: RunConn, status: str | None = None, limit: int = 200) -> list[RunDto]:
    safe_limit = max(1, min(limit, 1000))
    return [RunDto.from_row(row) for row in RunStore(conn).list_runs(status=status, limit=safe_limit)]


@router.post("/{run_id}/resume", response_model=RunDto)
def resume_run(run_id: int, conn: RunConn) -> RunDto:
    store = RunStore(conn)
    state = RunState(conn)

    row = store.get_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

    with conn:
        ts_ms = _now_ms()
        active_run_id = state.try_get_active_run_id()
        if active_run_id is not None and active_run_id != run_id:
            store.set_run_status(active_run_id, status="stopped", ts_ms=ts_ms)
            RunSegmentStore(conn).end_active_for_run(
                active_run_id,
                ended_ts_ms=ts_ms,
                ts_ms=ts_ms,
            )

        store.set_run_status(run_id, status="running", ts_ms=ts_ms)
        state.set_active_run(run_id)
        resumed = store.get_run(run_id)

    if resumed is None:
        raise HTTPException(status_code=500, detail="Run disappeared while resuming")
    return RunDto.from_row(resumed)


@router.get("/active", response_model=RunDto | None)
def active_run(conn: RunConn) -> RunDto | None:
    state = RunState(conn)
    run_id = state.try_get_active_run_id()
    if run_id is None:
        return None

    row = RunStore(conn).get_run(run_id)
    return RunDto.from_row(row) if row is not None else None


@router.get("/active/segments", response_model=list[RunSegmentDto])
def active_run_segments(conn: RunConn) -> list[RunSegmentDto]:
    state = RunState(conn)
    run_id = state.try_get_active_run_id()
    if run_id is None:
        return []
    return [RunSegmentDto.from_row(row) for row in RunSegmentStore(conn).list_for_run(run_id)]


@router.get("/{run_id}/segments", response_model=list[RunSegmentDto])
def list_run_segments(run_id: int, conn: RunConn) -> list[RunSegmentDto]:
    row = RunStore(conn).get_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return [RunSegmentDto.from_row(segment) for segment in RunSegmentStore(conn).list_for_run(run_id)]


def _now_ms() -> int:
    return time.time_ns() // 1_000_000
