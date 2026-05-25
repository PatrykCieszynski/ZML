from __future__ import annotations

from typing import Annotated

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
from zml_game_bridge.runtime.mining.tools import MiningToolService

router = APIRouter(prefix="/api/v1/mining/tools", tags=["mining-tools"])


def get_tool_service(runtime: RuntimeDep) -> MiningToolService:
    return runtime.mining_tool_service


ToolService = Annotated[MiningToolService, Depends(get_tool_service)]


@router.get("", response_model=list[MiningToolProfileDto])
def list_mining_tool_profiles(service: ToolService) -> list[MiningToolProfileDto]:
    return [MiningToolProfileDto.from_record(record) for record in service.list_profiles()]


@router.post("", response_model=MiningToolProfileDto)
def create_mining_tool_profile(
    request: CreateMiningToolProfileRequestDto,
    service: ToolService,
) -> MiningToolProfileDto:
    try:
        record = service.create_profile(
            kind=request.kind,
            name=request.name,
            decay_mpec=Mpec(request.decay_mpec),
            markup_percent=request.markup_percent,
            radius_m=request.radius_m,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return MiningToolProfileDto.from_record(record)


@router.delete("/{tool_id}", status_code=204)
def delete_mining_tool_profile(tool_id: str, service: ToolService) -> None:
    deleted = service.delete_profile(tool_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Mining tool not found: {tool_id}")


@router.get("/active", response_model=ActiveMiningToolsDto)
def get_active_mining_tools(service: ToolService) -> ActiveMiningToolsDto:
    return active_tools_dto(
        service.active_tools(),
        equipment_profile=service.get_equipment_profile(),
    )


@router.put("/active", response_model=ActiveMiningToolsDto)
def set_active_mining_tools(
    request: SetActiveMiningToolsRequestDto,
    service: ToolService,
) -> ActiveMiningToolsDto:
    try:
        active = service.set_active_tools(
            finder_id=request.finder_id,
            amp_id=request.amp_id,
            extractor_id=request.extractor_id,
            finder_range_enhancer_count=request.finder_range_enhancer_count,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return active_tools_dto(active, equipment_profile=service.get_equipment_profile())
