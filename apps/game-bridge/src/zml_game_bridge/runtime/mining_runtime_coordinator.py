from __future__ import annotations

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
from zml_game_bridge.inputs.ocr.signals import (
    FinderHitHintSignal,
    FinderModeInvalidatedSignal,
    FinderModesChangedSignal,
    FinderNoResourcesSignal,
    FinderUnitsChangedSignal,
    ProbeFiredSignal,
)

IdFactory = Callable[[], str]


@dataclass(frozen=True, slots=True)
class MiningRuntimeCoordinatorConfig:
    result_link_window_ms: int = 60_000


def default_mining_equipment_profile() -> MiningEquipmentProfile:
    return MiningEquipmentProfile(
        finder=MiningToolProfile(name="unknown-finder", decay_mpec=Mpec(0)),
    )


def default_id_factory() -> str:
    return uuid4().hex


class MiningRuntimeCoordinator:
    def __init__(
        self,
        *,
        profile: MiningEquipmentProfile | None = None,
        config: MiningRuntimeCoordinatorConfig | None = None,
        id_factory: IdFactory = default_id_factory,
    ) -> None:
        self._profile = profile or default_mining_equipment_profile()
        self._config = config or MiningRuntimeCoordinatorConfig()
        self._id_factory = id_factory
        self._modes_mask: int | None = None
        self._probes_per_drop: int | None = None
        self._ammo_per_drop: int | None = None
        self._pending_drop: MiningDropEvent | None = None

    def process(self, message: EventBase) -> list[EventBase]:
        if isinstance(message, FinderModesChangedSignal):
            self._modes_mask = message.modes_mask
            return []

        if isinstance(message, FinderModeInvalidatedSignal):
            self._modes_mask = None
            return []

        if isinstance(message, FinderUnitsChangedSignal):
            self._probes_per_drop = message.probes_per_drop
            self._ammo_per_drop = message.ammo_per_drop
            return []

        if isinstance(message, ProbeFiredSignal):
            return [self._record_drop(message)]

        if isinstance(message, FinderHitHintSignal):
            return [self._record_hit_hint(message)]

        if isinstance(message, FinderNoResourcesSignal):
            return [self._record_no_resources(message)]

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
            roi_name=signal.roi_name,
        )
        self._pending_drop = event
        return event

    def _record_hit_hint(self, signal: FinderHitHintSignal) -> MiningHitHintEvent:
        linked_drop = self._linked_pending_drop(signal.ts_ms)
        if linked_drop is not None:
            self._pending_drop = None

        return MiningHitHintEvent(
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
            roi_name=signal.roi_name,
        )

    def _record_no_resources(self, signal: FinderNoResourcesSignal) -> MiningNoResourcesEvent:
        linked_drop = self._linked_pending_drop(signal.ts_ms)
        if linked_drop is not None:
            self._pending_drop = None

        return MiningNoResourcesEvent(
            drop_id=linked_drop.drop_id if linked_drop is not None else None,
            observed_ts_ms=signal.ts_ms,
            position=linked_drop.position if linked_drop is not None else None,
            raw_status_text=signal.raw_status_text,
            roi_name=signal.roi_name,
        )

    def _linked_pending_drop(self, observed_ts_ms: int) -> MiningDropEvent | None:
        drop = self._pending_drop
        if drop is None:
            return None
        elapsed_ms = observed_ts_ms - drop.observed_ts_ms
        if 0 <= elapsed_ms <= self._config.result_link_window_ms:
            return drop
        self._pending_drop = None
        return None
