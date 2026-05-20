from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import uuid4

from zml_game_bridge.domain.mining_cost import MiningEquipmentProfile, MiningToolProfile
from zml_game_bridge.domain.money import Mpec

IdFactory = Callable[[], str]
DEFAULT_DROP_RADIUS_M = 55.0


@dataclass(frozen=True, slots=True)
class MiningCoordinatorConfig:
    result_link_window_ms: int = 60_000
    claim_depletion_link_max_distance_m: float = 120.0


def default_mining_equipment_profile() -> MiningEquipmentProfile:
    return MiningEquipmentProfile(
        finder=MiningToolProfile(
            name="unknown-finder",
            decay_mpec=Mpec(0),
            radius_m=DEFAULT_DROP_RADIUS_M,
        ),
    )


def default_id_factory() -> str:
    return uuid4().hex
