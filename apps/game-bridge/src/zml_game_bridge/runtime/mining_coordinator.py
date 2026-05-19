from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from uuid import uuid4

from zml_game_bridge.domain.mining_cost import (
    MiningEquipmentProfile,
    MiningToolProfile,
    calculate_drop_cost,
)
from zml_game_bridge.domain.mining_events import (
    MiningDropEvent,
    MiningHitHintEvent,
    MiningNoResourcesEvent,
)
from zml_game_bridge.domain.money import Mpec
from zml_game_bridge.events.base import EventBase
from zml_game_bridge.inputs.ocr.pipelines.mining_finder.signals import (
    FinderHitHintSignal,
    FinderModeInvalidatedSignal,
    FinderModesChangedSignal,
    FinderNoResourcesSignal,
    FinderUnitsChangedSignal,
    ProbeFiredSignal,
)

IdFactory = Callable[[], str]
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MiningCoordinatorConfig:
    result_link_window_ms: int = 60_000


def default_mining_equipment_profile() -> MiningEquipmentProfile:
    return MiningEquipmentProfile(
        finder=MiningToolProfile(name="unknown-finder", decay_mpec=Mpec(0)),
    )


def default_id_factory() -> str:
    return uuid4().hex


class MiningCoordinator:
    def __init__(
        self,
        *,
        profile: MiningEquipmentProfile | None = None,
        config: MiningCoordinatorConfig | None = None,
        id_factory: IdFactory = default_id_factory,
    ) -> None:
        self._profile = profile or default_mining_equipment_profile()
        self._config = config or MiningCoordinatorConfig()
        self._id_factory = id_factory
        self._modes_mask: int | None = None
        self._probes_per_drop: int | None = None
        self._ammo_per_drop: int | None = None
        self._pending_drop: MiningDropEvent | None = None

    def process(self, signal: EventBase) -> list[EventBase]:
        if isinstance(signal, FinderModesChangedSignal):
            self._modes_mask = signal.modes_mask
            return []

        if isinstance(signal, FinderModeInvalidatedSignal):
            self._modes_mask = None
            return []

        if isinstance(signal, FinderUnitsChangedSignal):
            self._probes_per_drop = signal.probes_per_drop
            self._ammo_per_drop = signal.ammo_per_drop
            return []

        if isinstance(signal, ProbeFiredSignal):
            return [self._record_drop(signal)]

        if isinstance(signal, FinderHitHintSignal):
            return [self._record_hit_hint(signal)]

        if isinstance(signal, FinderNoResourcesSignal):
            return [self._record_no_resources(signal)]

        return []

    def _record_drop(self, signal: ProbeFiredSignal) -> MiningDropEvent:
        modes_mask = signal.modes_mask if signal.modes_mask is not None else self._modes_mask
        probes_per_drop = (
            signal.probes_per_drop
            if signal.probes_per_drop is not None
            else self._probes_per_drop
        )
        ammo_per_drop = (
            signal.ammo_per_drop if signal.ammo_per_drop is not None else self._ammo_per_drop
        )

        if signal.probes_per_drop is not None:
            self._probes_per_drop = signal.probes_per_drop
        if signal.ammo_per_drop is not None:
            self._ammo_per_drop = signal.ammo_per_drop

        cost = calculate_drop_cost(
            profile=self._profile,
            ocr_ammo_per_drop=ammo_per_drop,
            ocr_probes_per_drop=probes_per_drop,
        )
        event = MiningDropEvent(
            drop_id=self._id_factory(),
            observed_ts_ms=signal.ts_ms,
            position=signal.position,
            modes_mask=modes_mask,
            probes_per_drop=probes_per_drop,
            ammo_per_drop=ammo_per_drop,
            cost=cost,
            raw_status_text=signal.raw_status_text,
        )
        self._pending_drop = event
        logger.info(
            "mining event derived type=%s drop_id=%s ts=%s position=%s modes=%s ammo=%s total_mpec=%s",
            type(event).__name__,
            event.drop_id,
            event.observed_ts_ms,
            event.position,
            event.modes_mask,
            event.ammo_per_drop,
            event.cost.total_mpec,
        )
        return event

    def _record_hit_hint(self, signal: FinderHitHintSignal) -> MiningHitHintEvent:
        linked_drop = self._linked_pending_drop(signal.ts_ms)
        if linked_drop is not None:
            self._pending_drop = None

        event = MiningHitHintEvent(
            hit_id=self._id_factory(),
            drop_id=linked_drop.drop_id if linked_drop is not None else None,
            observed_ts_ms=signal.ts_ms,
            position=linked_drop.position if linked_drop is not None else None,
            size_label=signal.size_label,
            size_index=signal.size_index,
            resource_name=signal.resource_name,
            range_m=signal.range_m,
            depth_m=signal.depth_m,
            raw_status_text=signal.raw_status_text,
            raw_details_text=signal.raw_details_text,
        )
        logger.info(
            "mining event derived type=%s hit_id=%s drop_id=%s ts=%s resource=%r size=%s(%s)",
            type(event).__name__,
            event.hit_id,
            event.drop_id,
            event.observed_ts_ms,
            event.resource_name,
            event.size_label,
            event.size_index,
        )
        return event

    def _record_no_resources(self, signal: FinderNoResourcesSignal) -> MiningNoResourcesEvent:
        linked_drop = self._linked_pending_drop(signal.ts_ms)
        if linked_drop is not None:
            self._pending_drop = None

        event = MiningNoResourcesEvent(
            drop_id=linked_drop.drop_id if linked_drop is not None else None,
            observed_ts_ms=signal.ts_ms,
            position=linked_drop.position if linked_drop is not None else None,
            raw_status_text=signal.raw_status_text,
        )
        logger.info(
            "mining event derived type=%s drop_id=%s ts=%s position=%s",
            type(event).__name__,
            event.drop_id,
            event.observed_ts_ms,
            event.position,
        )
        return event

    def _linked_pending_drop(self, observed_ts_ms: int) -> MiningDropEvent | None:
        drop = self._pending_drop
        if drop is None:
            return None
        elapsed_ms = observed_ts_ms - drop.observed_ts_ms
        if 0 <= elapsed_ms <= self._config.result_link_window_ms:
            return drop
        self._pending_drop = None
        return None
