from __future__ import annotations

from dataclasses import dataclass

from zml_game_bridge.domain.mining_cost import (
    MiningEquipmentProfile,
    MiningToolProfile,
    calculate_drop_cost,
)
from zml_game_bridge.domain.mining_events import MiningDropRecorded, MiningPreclaimDetected
from zml_game_bridge.domain.money import Mpec
from zml_game_bridge.events.base import EventBase
from zml_game_bridge.inputs.ocr.signals import (
    FinderHitHint,
    FinderModeInvalidated,
    FinderModesChanged,
    FinderUnitsChanged,
    ProbeFired,
)


@dataclass(frozen=True, slots=True)
class MiningSignalProcessorConfig:
    preclaim_link_window_ms: int = 60_000


def default_mining_equipment_profile() -> MiningEquipmentProfile:
    return MiningEquipmentProfile(
        finder=MiningToolProfile(name="unknown-finder", decay_mpec=Mpec(0)),
    )


class MiningSignalProcessor:
    def __init__(
        self,
        *,
        profile: MiningEquipmentProfile | None = None,
        config: MiningSignalProcessorConfig | None = None,
    ) -> None:
        self._profile = profile or default_mining_equipment_profile()
        self._config = config or MiningSignalProcessorConfig()
        self._modes_mask: int | None = None
        self._probes_per_drop: int | None = None
        self._ammo_per_drop: int | None = None
        self._last_drop: MiningDropRecorded | None = None

    def process(self, message: EventBase) -> list[EventBase]:
        if isinstance(message, FinderModesChanged):
            self._modes_mask = message.modes_mask
            return []

        if isinstance(message, FinderModeInvalidated):
            self._modes_mask = None
            return []

        if isinstance(message, FinderUnitsChanged):
            self._probes_per_drop = message.probes_per_drop
            self._ammo_per_drop = message.ammo_per_drop
            return []

        if isinstance(message, ProbeFired):
            return [self._record_drop(message)]

        if isinstance(message, FinderHitHint):
            return [self._record_preclaim(message)]

        return []

    def _record_drop(self, signal: ProbeFired) -> MiningDropRecorded:
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
        event = MiningDropRecorded(
            observed_ts_ms=signal.ts_ms,
            position=signal.position,
            modes_mask=modes_mask,
            probes_per_drop=probes_per_drop,
            ammo_per_drop=ammo_per_drop,
            cost=cost,
            raw_status_text=signal.raw_status_text,
            roi_name=signal.roi_name,
        )
        self._last_drop = event
        return event

    def _record_preclaim(self, signal: FinderHitHint) -> MiningPreclaimDetected:
        linked_drop = self._linked_drop(signal.ts_ms)
        return MiningPreclaimDetected(
            observed_ts_ms=signal.ts_ms,
            drop_observed_ts_ms=(
                linked_drop.observed_ts_ms if linked_drop is not None else None
            ),
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

    def _linked_drop(self, observed_ts_ms: int) -> MiningDropRecorded | None:
        drop = self._last_drop
        if drop is None:
            return None
        elapsed_ms = observed_ts_ms - drop.observed_ts_ms
        if 0 <= elapsed_ms <= self._config.preclaim_link_window_ms:
            return drop
        return None
