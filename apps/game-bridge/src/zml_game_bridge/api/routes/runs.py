from __future__ import annotations

from fastapi import APIRouter, HTTPException

from zml_game_bridge.api.dependencies import ReadConn, RuntimeDep
from zml_game_bridge.api.schemas.runs import (
    RunDto,
    RunSegmentDto,
    StartRunRequestDto,
    StopRunRequestDto,
    UpdateRunRequestDto,
)
from zml_game_bridge.application.runs.commands import (
    InvalidRunCommandError,
    NoActiveRunError,
    ResumeRunCommand,
    RunCommandError,
    RunNotFoundError,
    StartRunCommand,
    StopRunCommand,
    UpdateRunCommand,
)
from zml_game_bridge.persistence.run_state import RunState
from zml_game_bridge.persistence.runs import RunRow, RunSegmentStore, RunStore
from zml_game_bridge.runtime.runtime import AppRuntime
from zml_game_bridge.runtime.runtime_commands import RuntimeCommand

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])


@router.post("/start", response_model=RunDto)
def start_run(request: StartRunRequestDto, runtime: RuntimeDep) -> RunDto:
    row = _execute_run_command(runtime, StartRunCommand(name=request.name, notes=request.notes))
    return RunDto.from_row(row)


@router.post("/stop", response_model=RunDto)
def stop_run(request: StopRunRequestDto, runtime: RuntimeDep) -> RunDto:
    row = _execute_run_command(runtime, StopRunCommand(run_id=request.run_id))
    return RunDto.from_row(row)


@router.get("", response_model=list[RunDto])
def list_runs(conn: ReadConn, status: str | None = None, limit: int = 200) -> list[RunDto]:
    safe_limit = max(1, min(limit, 1000))
    return [
        RunDto.from_row(row) for row in RunStore(conn).list_runs(status=status, limit=safe_limit)
    ]


@router.post("/{run_id}/resume", response_model=RunDto)
def resume_run(run_id: int, runtime: RuntimeDep) -> RunDto:
    row = _execute_run_command(runtime, ResumeRunCommand(run_id=run_id))
    return RunDto.from_row(row)


@router.patch("/{run_id}", response_model=RunDto)
def update_run(run_id: int, request: UpdateRunRequestDto, runtime: RuntimeDep) -> RunDto:
    row = _execute_run_command(
        runtime,
        UpdateRunCommand(
            run_id=run_id,
            name=request.name,
            notes=request.notes,
            notes_set="notes" in request.model_fields_set,
        ),
    )
    return RunDto.from_row(row)


@router.get("/active", response_model=RunDto | None)
def active_run(conn: ReadConn) -> RunDto | None:
    state = RunState(conn)
    run_id = state.try_get_active_run_id()
    if run_id is None:
        return None

    row = RunStore(conn).get_run(run_id)
    return RunDto.from_row(row) if row is not None else None


@router.get("/active/segments", response_model=list[RunSegmentDto])
def active_run_segments(conn: ReadConn) -> list[RunSegmentDto]:
    state = RunState(conn)
    run_id = state.try_get_active_run_id()
    if run_id is None:
        return []
    return [RunSegmentDto.from_row(row) for row in RunSegmentStore(conn).list_for_run(run_id)]


@router.get("/{run_id}/segments", response_model=list[RunSegmentDto])
def list_run_segments(run_id: int, conn: ReadConn) -> list[RunSegmentDto]:
    row = RunStore(conn).get_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")
    return [
        RunSegmentDto.from_row(segment) for segment in RunSegmentStore(conn).list_for_run(run_id)
    ]


def _execute_run_command(runtime: AppRuntime, command: RuntimeCommand[RunRow]) -> RunRow:
    try:
        return runtime.execute_runtime_command(command)
    except InvalidRunCommandError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (NoActiveRunError, RunNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RunCommandError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
