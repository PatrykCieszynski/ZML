from __future__ import annotations

from collections.abc import Callable, Iterable

from zml_game_bridge.domain.mining_cost import MiningEquipmentProfile, calculate_extraction_cost
from zml_game_bridge.events.base import EventBase
from zml_game_bridge.resources.mining_resources import MiningResourceCatalog
from zml_game_bridge.runtime.mining.chat_correlator import MiningChatCorrelator
from zml_game_bridge.runtime.mining.claim_lifecycle import (
    ActiveClaim,
    ClaimLifecycleCorrelator,
    PositionProvider,
)
from zml_game_bridge.runtime.mining.finder_correlator import (
    DropRunContextProvider,
    FinderDropCorrelator,
)
from zml_game_bridge.runtime.mining.settings import (
    IdFactory,
    MiningCoordinatorConfig,
    default_id_factory,
    default_mining_equipment_profile,
)

MiningEquipmentProfileProvider = Callable[[], MiningEquipmentProfile]


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
            extraction_cost_provider=lambda: calculate_extraction_cost(
                resolved_profile_provider()
            ),
        )
        self._claim_lifecycle = ClaimLifecycleCorrelator(
            config=resolved_config,
            id_factory=id_factory,
            position_provider=position_provider,
        )

    def restore_active_claims(self, claims: Iterable[ActiveClaim]) -> None:
        self._claim_lifecycle.restore_active_claims(claims)

    def process(self, signal: EventBase) -> list[EventBase]:
        derived_events: list[EventBase] = []
        correlated_events: list[EventBase] = []
        correlated_events.extend(self._finder.process(signal))
        correlated_events.extend(self._chat.process(signal))

        for event in correlated_events:
            derived_events.append(event)
            derived_events.extend(self._claim_lifecycle.process_event(event))

        derived_events.extend(self._claim_lifecycle.process_signal(signal))
        return derived_events
