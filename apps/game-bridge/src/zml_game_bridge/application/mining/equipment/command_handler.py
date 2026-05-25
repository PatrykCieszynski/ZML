from __future__ import annotations

from typing import TypeVar, cast

from zml_game_bridge.application.mining.equipment.commands import (
    CreateMiningToolProfileCommand,
    DeleteMiningToolProfileCommand,
    MiningToolNotFoundError,
    SetActiveMiningToolsCommand,
)
from zml_game_bridge.application.mining.equipment.service import (
    ActiveMiningTools,
    MiningEquipmentService,
    MiningToolProfileRecord,
)
from zml_game_bridge.runtime.runtime_commands import (
    RuntimeCommand,
    RuntimeCommandResult,
    UnsupportedRuntimeCommandError,
)

T = TypeVar("T")


class MiningEquipmentCommandHandler:
    """Runtime command handler for mutable mining equipment configuration."""

    def __init__(self, *, equipment_service: MiningEquipmentService) -> None:
        self._equipment_service = equipment_service

    def process_command(self, command: RuntimeCommand[T]) -> RuntimeCommandResult[T]:
        if isinstance(command, CreateMiningToolProfileCommand):
            record = self._equipment_service.create_profile(
                kind=command.kind,
                name=command.name,
                decay_mpec=command.decay_mpec,
                markup_percent=command.markup_percent,
                radius_m=command.radius_m,
            )
            return cast(
                RuntimeCommandResult[T],
                RuntimeCommandResult[MiningToolProfileRecord](value=record),
            )

        if isinstance(command, DeleteMiningToolProfileCommand):
            deleted = self._equipment_service.delete_profile(command.tool_id)
            if not deleted:
                raise MiningToolNotFoundError(command.tool_id)
            return cast(RuntimeCommandResult[T], RuntimeCommandResult[None](value=None))

        if isinstance(command, SetActiveMiningToolsCommand):
            active = self._equipment_service.set_active_tools(
                finder_id=command.finder_id,
                amp_id=command.amp_id,
                extractor_id=command.extractor_id,
                finder_range_enhancer_count=command.finder_range_enhancer_count,
            )
            return cast(
                RuntimeCommandResult[T],
                RuntimeCommandResult[ActiveMiningTools](value=active),
            )

        raise UnsupportedRuntimeCommandError(type(command).__name__)
