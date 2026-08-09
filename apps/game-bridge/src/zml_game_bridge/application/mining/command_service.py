from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar, cast

from zml_game_bridge.application.mining.claims.commands import (
    ExpireMiningClaimsCommand,
    IgnoreMiningClaimCommand,
    MarkMiningClaimDepletedCommand,
    ResolvePendingDropResultsCommand,
)
from zml_game_bridge.application.mining.claims.lifecycle import ClaimLifecycleCorrelator
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
from zml_game_bridge.application.runs.commands import (
    DeleteRunCommand,
    ResumeRunCommand,
    StartRunCommand,
    StopRunCommand,
    UpdateRunCommand,
)
from zml_game_bridge.persistence.runs import RunRow
from zml_game_bridge.runtime.db_commands import DbCommand
from zml_game_bridge.runtime.runtime_commands import (
    RuntimeCommand,
    RuntimeCommandResult,
    UnsupportedRuntimeCommandError,
)

T = TypeVar("T")

_RUN_COMMAND_TYPES = (
    StartRunCommand,
    StopRunCommand,
    ResumeRunCommand,
    UpdateRunCommand,
    DeleteRunCommand,
)


class MiningCommandService:
    """Single runtime command boundary for mining-facing application commands."""

    def __init__(
        self,
        *,
        claim_lifecycle: ClaimLifecycleCorrelator | None = None,
        db_command_executor: Callable[[DbCommand[Any]], Any] | None = None,
        mining_equipment_service: MiningEquipmentService | None = None,
    ) -> None:
        self._claim_lifecycle = claim_lifecycle
        self._db_command_executor = db_command_executor
        self._mining_equipment_service = mining_equipment_service

    def process_command(self, command: RuntimeCommand[T]) -> RuntimeCommandResult[T]:
        if isinstance(command, MarkMiningClaimDepletedCommand):
            claim_lifecycle = self._require_claim_lifecycle(command)
            event = claim_lifecycle.deplete_claim(command)
            return cast(
                RuntimeCommandResult[T],
                RuntimeCommandResult[None](value=None, events=(event,)),
            )

        if isinstance(command, IgnoreMiningClaimCommand):
            claim_lifecycle = self._require_claim_lifecycle(command)
            event = claim_lifecycle.ignore_claim(command)
            return cast(
                RuntimeCommandResult[T],
                RuntimeCommandResult[None](value=None, events=(event,)),
            )

        if isinstance(command, ExpireMiningClaimsCommand):
            claim_lifecycle = self._require_claim_lifecycle(command)
            events = claim_lifecycle.expire_claims(command)
            return cast(
                RuntimeCommandResult[T],
                RuntimeCommandResult[int](value=len(events), events=tuple(events)),
            )

        if isinstance(command, ResolvePendingDropResultsCommand):
            claim_lifecycle = self._require_claim_lifecycle(command)
            events = claim_lifecycle.resolve_pending_drop_results(command)
            return cast(
                RuntimeCommandResult[T],
                RuntimeCommandResult[int](value=len(events), events=tuple(events)),
            )

        if isinstance(command, CreateMiningToolProfileCommand):
            equipment = self._require_equipment_service(command)
            record = equipment.create_profile(
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
            equipment = self._require_equipment_service(command)
            deleted = equipment.delete_profile(command.tool_id)
            if not deleted:
                raise MiningToolNotFoundError(command.tool_id)
            return cast(RuntimeCommandResult[T], RuntimeCommandResult[None](value=None))

        if isinstance(command, SetActiveMiningToolsCommand):
            equipment = self._require_equipment_service(command)
            active = equipment.set_active_tools(
                finder_id=command.finder_id,
                amp_id=command.amp_id,
                extractor_id=command.extractor_id,
                finder_range_enhancer_count=command.finder_range_enhancer_count,
            )
            return cast(
                RuntimeCommandResult[T],
                RuntimeCommandResult[ActiveMiningTools](value=active),
            )

        if isinstance(command, _RUN_COMMAND_TYPES):
            if self._db_command_executor is None:
                raise UnsupportedRuntimeCommandError(type(command).__name__)
            result = self._db_command_executor(cast(DbCommand[RunRow], command))
            return cast(RuntimeCommandResult[T], RuntimeCommandResult(value=result))

        raise UnsupportedRuntimeCommandError(type(command).__name__)

    def _require_claim_lifecycle(
        self,
        command: RuntimeCommand[Any],
    ) -> ClaimLifecycleCorrelator:
        if self._claim_lifecycle is None:
            raise UnsupportedRuntimeCommandError(type(command).__name__)
        return self._claim_lifecycle

    def _require_equipment_service(
        self,
        command: RuntimeCommand[Any],
    ) -> MiningEquipmentService:
        if self._mining_equipment_service is None:
            raise UnsupportedRuntimeCommandError(type(command).__name__)
        return self._mining_equipment_service
