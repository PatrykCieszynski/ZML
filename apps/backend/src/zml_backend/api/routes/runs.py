from __future__ import annotations

from typing import Never

from fastapi import APIRouter, HTTPException

from zml_backend.api.dependencies import ReadConn, RuntimeDep
from zml_backend.api.schemas.runs import (
    MoveRunSegmentRequestDto,
    RunDto,
    RunSegmentDto,
    SplitRunSegmentRequestDto,
    StartRunRequestDto,
    StopRunRequestDto,
    UpdateRunRequestDto,
    UpdateRunSegmentSetupRequestDto,
)
from zml_backend.application.mining.equipment.service import MiningToolKind
from zml_backend.application.mining.settings import default_id_factory
from zml_backend.application.runs.commands import (
    DeleteRunCommand,
    InvalidRunCommandError,
    NoActiveRunError,
    ResumeRunCommand,
    RunCommandError,
    RunNotFoundError,
    StartRunCommand,
    StopRunCommand,
    UpdateRunCommand,
)
from zml_backend.application.runs.segment_corrections import (
    InvalidSegmentCorrectionError,
    MoveRunSegmentCommand,
    SegmentCorrectionError,
    SegmentNotFoundError,
    SplitRunSegmentCommand,
    UpdateRunSegmentSetupCommand,
)
from zml_backend.domain.mining_cost import MiningToolProfile
from zml_backend.persistence.run_state import RunState
from zml_backend.persistence.runs import RunRow, RunSegmentStore, RunStore
from zml_backend.runtime.runtime import AppRuntime
from zml_backend.runtime.runtime_commands import RuntimeCommand

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
def list_runs(
    conn: ReadConn,
    status: str | None = None,
    include_deleted: bool = False,
    limit: int = 200,
) -> list[RunDto]:
    safe_limit = max(1, min(limit, 1000))
    return [
        RunDto.from_row(row)
        for row in RunStore(conn).list_runs(
            status=status,
            include_deleted=include_deleted,
            limit=safe_limit,
        )
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


@router.delete("/{run_id}", response_model=RunDto)
def delete_run(run_id: int, runtime: RuntimeDep) -> RunDto:
    row = _execute_run_command(runtime, DeleteRunCommand(run_id=run_id))
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


@router.patch("/{run_id}/segments/{segment_id}/setup", response_model=RunSegmentDto)
def update_run_segment_setup(
    run_id: int,
    segment_id: str,
    request: UpdateRunSegmentSetupRequestDto,
    runtime: RuntimeDep,
) -> RunSegmentDto:
    finder_set = "finder_tool_id" in request.model_fields_set
    amp_set = "amp_tool_id" in request.model_fields_set
    if not finder_set and not amp_set:
        raise HTTPException(status_code=422, detail="Finder or amplifier correction is required")

    finder = (
        _resolve_tool(runtime, request.finder_tool_id, "finder", required=True)
        if finder_set
        else None
    )
    amp = _resolve_tool(runtime, request.amp_tool_id, "amp", required=False) if amp_set else None
    try:
        row = runtime.execute_db_command(
            UpdateRunSegmentSetupCommand(
                run_id=run_id,
                segment_id=segment_id,
                finder_set=finder_set,
                finder=finder,
                amp_set=amp_set,
                amp=amp,
            )
        )
    except SegmentCorrectionError as exc:
        _raise_segment_correction_http(exc)
    runtime.refresh_after_segment_correction()
    return RunSegmentDto.from_row(row)


@router.post("/{run_id}/segments/{segment_id}/split", response_model=RunSegmentDto)
def split_run_segment(
    run_id: int,
    segment_id: str,
    request: SplitRunSegmentRequestDto,
    runtime: RuntimeDep,
) -> RunSegmentDto:
    finder_set = "finder_tool_id" in request.model_fields_set
    amp_set = "amp_tool_id" in request.model_fields_set
    finder = (
        _resolve_tool(runtime, request.finder_tool_id, "finder", required=True)
        if finder_set
        else None
    )
    amp = _resolve_tool(runtime, request.amp_tool_id, "amp", required=False) if amp_set else None
    try:
        row = runtime.execute_db_command(
            SplitRunSegmentCommand(
                run_id=run_id,
                segment_id=segment_id,
                selection=request.selection,
                drop_count=request.drop_count,
                new_segment_id=default_id_factory(),
                finder_set=finder_set,
                finder=finder,
                amp_set=amp_set,
                amp=amp,
            )
        )
    except SegmentCorrectionError as exc:
        _raise_segment_correction_http(exc)
    runtime.refresh_after_segment_correction()
    return RunSegmentDto.from_row(row)


@router.post("/{run_id}/segments/{segment_id}/move", response_model=RunSegmentDto)
def move_run_segment(
    run_id: int,
    segment_id: str,
    request: MoveRunSegmentRequestDto,
    runtime: RuntimeDep,
) -> RunSegmentDto:
    try:
        row = runtime.execute_db_command(
            MoveRunSegmentCommand(
                run_id=run_id,
                segment_id=segment_id,
                target_run_id=request.target_run_id,
                new_run_name=request.new_run_name,
            )
        )
    except SegmentCorrectionError as exc:
        _raise_segment_correction_http(exc)
    runtime.refresh_after_segment_correction()
    return RunSegmentDto.from_row(row)


def _resolve_tool(
    runtime: AppRuntime,
    tool_id: str | None,
    expected_kind: MiningToolKind,
    *,
    required: bool,
) -> MiningToolProfile | None:
    if tool_id is None:
        if required:
            raise HTTPException(status_code=422, detail=f"{expected_kind.title()} is required")
        return None
    record = runtime.mining_equipment_service.get_profile(tool_id)
    if record is None or record.kind != expected_kind:
        raise HTTPException(status_code=422, detail=f"Unknown {expected_kind} tool: {tool_id}")
    return record.to_tool_profile()


def _raise_segment_correction_http(exc: SegmentCorrectionError) -> Never:
    if isinstance(exc, SegmentNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, InvalidSegmentCorrectionError):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


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
