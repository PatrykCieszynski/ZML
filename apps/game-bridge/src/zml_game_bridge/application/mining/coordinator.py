from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, Protocol

from zml_game_bridge.application.mining.chat.correlator import MiningChatCorrelator
from zml_game_bridge.application.mining.claims.lifecycle import (
    ActiveClaim,
    ClaimLifecycleCorrelator,
    PositionProvider,
)
from zml_game_bridge.application.mining.drops.finder_correlator import (
    DropRunContextProvider,
    FinderDropCorrelator,
)
from zml_game_bridge.application.mining.settings import (
    IdFactory,
    MiningCoordinatorConfig,
    default_id_factory,
    default_mining_equipment_profile,
)
from zml_game_bridge.application.mining.setup.command_handler import MiningSetupCommandHandler
from zml_game_bridge.application.mining.setup.tools import MiningToolService
from zml_game_bridge.application.runs.command_handler import RunCommandHandler
from zml_game_bridge.domain.mining_cost import MiningEquipmentProfile, calculate_extraction_cost
from zml_game_bridge.events.base import EventBase
from zml_game_bridge.resources.mining_resources import MiningResourceCatalog
from zml_game_bridge.runtime.db_commands import DbCommand
from zml_game_bridge.runtime.runtime_commands import (
    RuntimeCommand,
    RuntimeCommandResult,
    UnsupportedRuntimeCommandError,
)

MiningEquipmentProfileProvider = Callable[[], MiningEquipmentProfile]


class SignalCorrelator(Protocol):
    def process(self, signal: EventBase) -> Iterable[EventBase]:
        """Derive durable events from one input signal."""
        ...


class DerivedEventHandler(Protocol):
    def process_event(self, event: EventBase) -> Iterable[EventBase]:
        """React to events derived earlier in this coordinator cycle."""
        ...


class SignalHandler(Protocol):
    def process_signal(self, signal: EventBase) -> Iterable[EventBase]:
        """React directly to an input signal without producing an upstream event first."""
        ...


class CommandHandler(Protocol):
    def process_command[T](self, command: RuntimeCommand[T]) -> RuntimeCommandResult[T]:
        """Handle one runtime command type or raise UnsupportedRuntimeCommandError."""
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
        db_command_executor: Callable[[DbCommand[Any]], Any] | None = None,
        mining_tool_service: MiningToolService | None = None,
    ) -> None:
        resolved_profile = profile or default_mining_equipment_profile()
        resolved_profile_provider = profile_provider or (lambda: resolved_profile)
        resolved_config = config or MiningCoordinatorConfig()
        self._finder = FinderDropCorrelator(
            profile_provider=resolved_profile_provider,
            run_context_provider=run_context_provider,
            config=resolved_config,
            id_factory=id_factory,
        )
        self._chat = MiningChatCorrelator(
            resource_catalog=resource_catalog,
            extraction_cost_provider=lambda: calculate_extraction_cost(resolved_profile_provider()),
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

        run_commands = (
            RunCommandHandler(db_command_executor=db_command_executor)
            if db_command_executor is not None
            else None
        )
        setup_commands = (
            MiningSetupCommandHandler(tool_service=mining_tool_service)
            if mining_tool_service is not None
            else None
        )
        self._command_handlers: tuple[CommandHandler, ...] = tuple(
            handler for handler in (run_commands, setup_commands) if handler is not None
        )

    def restore_active_claims(self, claims: Iterable[ActiveClaim]) -> None:
        self._claim_lifecycle.restore_active_claims(claims)

    def process(self, signal: EventBase) -> list[EventBase]:
        derived_events: list[EventBase] = []
        correlated_events: list[EventBase] = []
        for correlator in self._signal_correlators:
            correlated_events.extend(correlator.process(signal))

        for event in correlated_events:
            derived_events.append(event)
            for handler in self._derived_event_handlers:
                derived_events.extend(handler.process_event(event))

        for handler in self._direct_signal_handlers:
            derived_events.extend(handler.process_signal(signal))
        return derived_events

    def process_command[T](self, command: RuntimeCommand[T]) -> RuntimeCommandResult[T]:
        last_error: UnsupportedRuntimeCommandError | None = None
        for processor in self._command_handlers:
            try:
                return processor.process_command(command)
            except UnsupportedRuntimeCommandError as exc:
                last_error = exc
        raise last_error or UnsupportedRuntimeCommandError(type(command).__name__)
