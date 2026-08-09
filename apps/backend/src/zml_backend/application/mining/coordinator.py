from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, Protocol

from zml_backend.application.mining.chat.correlator import MiningChatCorrelator
from zml_backend.application.mining.claims.lifecycle import (
    ActiveClaim,
    ClaimLifecycleCorrelator,
)
from zml_backend.application.mining.command_service import MiningCommandService
from zml_backend.application.mining.drops.finder_correlator import (
    DropRunContextProvider,
    FinderDropCorrelator,
)
from zml_backend.application.mining.equipment.service import MiningEquipmentService
from zml_backend.application.mining.loot import MiningLootRecorder
from zml_backend.application.mining.settings import (
    IdFactory,
    MiningCoordinatorConfig,
    default_id_factory,
    default_mining_equipment_profile,
)
from zml_backend.application.position.provider import PositionProvider
from zml_backend.domain.mining_cost import MiningEquipmentProfile, calculate_extraction_cost
from zml_backend.domain.mining_events import MiningLootTotalsUpdatedEvent
from zml_backend.domain.money import Mpec
from zml_backend.events.base import EventBase, SignalBase
from zml_backend.inputs.chat.signals import ItemReceivedSignal
from zml_backend.resources.mining_resources import MiningResourceCatalog
from zml_backend.runtime.db_commands import DbCommand
from zml_backend.runtime.runtime_commands import RuntimeCommand, RuntimeCommandResult

MiningEquipmentProfileProvider = Callable[[], MiningEquipmentProfile]
RunIdProvider = Callable[[], int | None]
SegmentIdProvider = Callable[[], str | None]


class SignalCorrelator(Protocol):
    def process_signal(self, signal: SignalBase) -> Iterable[EventBase]:
        """Derive durable events from one input signal."""
        ...


class DerivedEventHandler(Protocol):
    def process_event(self, event: EventBase) -> Iterable[EventBase]:
        """React to events derived earlier in this coordinator cycle."""
        ...


class SignalHandler(Protocol):
    def process_signal(self, signal: SignalBase) -> Iterable[EventBase]:
        """React directly to an input signal without producing an upstream event first."""
        ...


class MiningCoordinator:
    def __init__(
        self,
        *,
        profile: MiningEquipmentProfile | None = None,
        profile_provider: MiningEquipmentProfileProvider | None = None,
        config: MiningCoordinatorConfig | None = None,
        id_factory: IdFactory = default_id_factory,
        position_provider: PositionProvider | None = None,
        resource_catalog: MiningResourceCatalog | None = None,
        run_context_provider: DropRunContextProvider | None = None,
        run_id_provider: RunIdProvider | None = None,
        segment_id_provider: SegmentIdProvider | None = None,
        db_command_executor: Callable[[DbCommand[Any]], Any] | None = None,
        mining_equipment_service: MiningEquipmentService | None = None,
    ) -> None:
        resolved_profile = profile or default_mining_equipment_profile()
        resolved_profile_provider = profile_provider or (lambda: resolved_profile)
        resolved_config = config or MiningCoordinatorConfig()
        self._finder = FinderDropCorrelator(
            profile_provider=resolved_profile_provider,
            run_context_provider=run_context_provider,
            position_provider=position_provider,
            config=resolved_config,
            id_factory=id_factory,
        )
        loot_recorder: (
            Callable[
                [ItemReceivedSignal, Mpec | None, int | None, str | None],
                MiningLootTotalsUpdatedEvent | None,
            ]
            | None
        ) = None
        if db_command_executor is not None:
            loot_service = MiningLootRecorder(db_command_executor)

            def record_loot_item(
                signal: ItemReceivedSignal,
                extraction_cost_mpec: Mpec | None,
                run_id: int | None,
                segment_id: str | None,
            ) -> MiningLootTotalsUpdatedEvent | None:
                return loot_service.record_item(
                    signal,
                    extraction_cost_mpec=extraction_cost_mpec,
                    run_id=run_id,
                    segment_id=segment_id,
                )

            loot_recorder = record_loot_item
        self._chat = MiningChatCorrelator(
            resource_catalog=resource_catalog,
            extraction_cost_provider=lambda: calculate_extraction_cost(resolved_profile_provider()),
            run_id_provider=run_id_provider,
            segment_id_provider=segment_id_provider,
            loot_recorder=loot_recorder,
        )
        self._claim_lifecycle = ClaimLifecycleCorrelator(
            config=resolved_config,
            id_factory=id_factory,
            position_provider=position_provider,
            resource_catalog=resource_catalog,
        )
        self._signal_correlators: tuple[SignalCorrelator, ...] = (self._finder, self._chat)
        self._derived_event_handlers: tuple[DerivedEventHandler, ...] = (self._claim_lifecycle,)
        self._direct_signal_handlers: tuple[SignalHandler, ...] = (self._claim_lifecycle,)

        self._commands = MiningCommandService(
            claim_lifecycle=self._claim_lifecycle,
            db_command_executor=db_command_executor,
            mining_equipment_service=mining_equipment_service,
        )

    def restore_active_claims(self, claims: Iterable[ActiveClaim]) -> None:
        self._claim_lifecycle.restore_active_claims(claims)

    def process_signal(self, signal: SignalBase) -> list[EventBase]:
        derived_events: list[EventBase] = []
        correlated_events: list[EventBase] = []
        for correlator in self._signal_correlators:
            correlated_events.extend(correlator.process_signal(signal))

        for event in correlated_events:
            derived_events.append(event)
            for handler in self._derived_event_handlers:
                derived_events.extend(handler.process_event(event))

        for handler in self._direct_signal_handlers:
            derived_events.extend(handler.process_signal(signal))
        return derived_events

    def process_command[T](self, command: RuntimeCommand[T]) -> RuntimeCommandResult[T]:
        return self._commands.process_command(command)
