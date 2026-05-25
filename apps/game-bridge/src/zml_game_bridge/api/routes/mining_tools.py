from __future__ import annotations

from typing import Annotated, TypeVar

from fastapi import APIRouter, Depends, HTTPException

from zml_game_bridge.api.dependencies import RuntimeDep
from zml_game_bridge.api.schemas.mining_tools import (
    ActiveMiningToolsDto,
    CreateMiningToolProfileRequestDto,
    MiningToolProfileDto,
    SetActiveMiningToolsRequestDto,
    active_tools_dto,
)
from zml_game_bridge.domain.money import Mpec
from zml_game_bridge.runtime.mining.tool_commands import (
    CreateMiningToolProfileCommand,
    DeleteMiningToolProfileCommand,
    MiningToolCommandError,
    MiningToolNotFoundError,
    SetActiveMiningToolsCommand,
)
from zml_game_bridge.runtime.mining.tools import MiningToolService
from zml_game_bridge.runtime.runtime import AppRuntime
from zml_game_bridge.runtime.runtime_commands import RuntimeCommand

router = APIRouter(prefix="/api/v1/mining/tools", tags=["mining-tools"])
T = TypeVar("T")


def get_tool_service(runtime: RuntimeDep) -> MiningToolService:
    return runtime.mining_tool_service


ToolService = Annotated[MiningToolService, Depends(get_tool_service)]


@router.get("", response_model=list[MiningToolProfileDto])
def list_mining_tool_profiles(service: ToolService) -> list[MiningToolProfileDto]:
    return [MiningToolProfileDto.from_record(record) for record in service.list_profiles()]


@router.post("", response_model=MiningToolProfileDto)
def create_mining_tool_profile(
    request: CreateMiningToolProfileRequestDto,
    runtime: RuntimeDep,
) -> MiningToolProfileDto:
    record = _execute_tool_command(
        runtime,
        CreateMiningToolProfileCommand(
            kind=request.kind,
            name=request.name,
            decay_mpec=Mpec(request.decay_mpec),
            markup_percent=request.markup_percent,
            radius_m=request.radius_m,
        ),
    )
    return MiningToolProfileDto.from_record(record)


@router.delete("/{tool_id}", status_code=204)
def delete_mining_tool_profile(tool_id: str, runtime: RuntimeDep) -> None:
    _execute_tool_command(runtime, DeleteMiningToolProfileCommand(tool_id=tool_id))


@router.get("/active", response_model=ActiveMiningToolsDto)
def get_active_mining_tools(service: ToolService) -> ActiveMiningToolsDto:
    return active_tools_dto(
        service.active_tools(),
        equipment_profile=service.get_equipment_profile(),
    )


@router.put("/active", response_model=ActiveMiningToolsDto)
def set_active_mining_tools(
    request: SetActiveMiningToolsRequestDto,
    runtime: RuntimeDep,
) -> ActiveMiningToolsDto:
    active = _execute_tool_command(
        runtime,
        SetActiveMiningToolsCommand(
            finder_id=request.finder_id,
            amp_id=request.amp_id,
            extractor_id=request.extractor_id,
            finder_range_enhancer_count=request.finder_range_enhancer_count,
        ),
    )
    return active_tools_dto(
        active,
        equipment_profile=runtime.mining_tool_service.get_equipment_profile(),
    )


def _execute_tool_command(runtime: AppRuntime, command: RuntimeCommand[T]) -> T:
    try:
        return runtime.execute_runtime_command(command)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except MiningToolNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except MiningToolCommandError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
