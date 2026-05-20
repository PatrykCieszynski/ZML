from __future__ import annotations

from zml_game_bridge.domain.mining_cost import MiningEquipmentProfile
from zml_game_bridge.events.base import EventBase
from zml_game_bridge.runtime.mining.chat_correlator import MiningChatCorrelator
from zml_game_bridge.runtime.mining.finder_correlator import FinderDropCorrelator
from zml_game_bridge.runtime.mining.settings import (
    IdFactory,
    MiningCoordinatorConfig,
    default_id_factory,
    default_mining_equipment_profile,
)


class MiningCoordinator:
    def __init__(
        self,
        *,
        profile: MiningEquipmentProfile | None = None,
        config: MiningCoordinatorConfig | None = None,
        id_factory: IdFactory = default_id_factory,
    ) -> None:
        resolved_profile = profile or default_mining_equipment_profile()
        resolved_config = config or MiningCoordinatorConfig()
        self._finder = FinderDropCorrelator(
            profile=resolved_profile,
            config=resolved_config,
            id_factory=id_factory,
        )
        self._chat = MiningChatCorrelator()

    def process(self, signal: EventBase) -> list[EventBase]:
        derived_events: list[EventBase] = []
        derived_events.extend(self._finder.process(signal))
        derived_events.extend(self._chat.process(signal))
        return derived_events
