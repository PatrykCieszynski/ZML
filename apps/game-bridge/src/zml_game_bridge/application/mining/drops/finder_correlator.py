from __future__ import annotations

import logging
from collections.abc import Callable

from zml_game_bridge.application.mining.segments.session import DropRunContext, MiningSegmentSetup
from zml_game_bridge.application.mining.settings import (
    DEFAULT_DROP_RADIUS_M,
    IdFactory,
    MiningCoordinatorConfig,
)
from zml_game_bridge.application.position.provider import PositionProvider
from zml_game_bridge.domain.claim_size import expected_claim_expires_ts_ms
from zml_game_bridge.domain.mining_cost import (
    MiningEquipmentProfile,
    calculate_drop_cost,
    effective_finder_radius_m,
)
from zml_game_bridge.domain.mining_events import (
    MiningDropEvent,
    MiningHitHintEvent,
    MiningNoResourcesEvent,
)
from zml_game_bridge.domain.position import WorldPos
from zml_game_bridge.events.base import EventBase, SignalBase
from zml_game_bridge.inputs.ocr.pipelines.mining_finder.signals import (
    FinderHitHintSignal,
    FinderModeInvalidatedSignal,
    FinderModesChangedSignal,
    FinderNoResourcesSignal,
    FinderUnitsChangedSignal,
    ProbeFiredSignal,
)

logger = logging.getLogger(__name__)
MiningEquipmentProfileProvider = Callable[[], MiningEquipmentProfile]
DropRunContextProvider = Callable[
    [int, MiningSegmentSetup],
    DropRunContext,
]


class FinderDropCorrelator:
    def __init__(
        self,
        *,
        profile_provider: MiningEquipmentProfileProvider,
        run_context_provider: DropRunContextProvider | None = None,
        position_provider: PositionProvider | None = None,
        config: MiningCoordinatorConfig,
        id_factory: IdFactory,
    ) -> None:
        self._profile_provider = profile_provider
        self._run_context_provider = run_context_provider
        self._position_provider = position_provider or _none_position_provider
        self._config = config
        self._id_factory = id_factory
        self._modes_mask: int | None = None
        self._probes_per_drop: int | None = None
        self._ammo_per_drop: int | None = None
        self._pending_drop: MiningDropEvent | None = None
        self._last_accepted_probe_ts_ms: int | None = None

    def process_signal(self, signal: SignalBase) -> list[EventBase]:
        if isinstance(signal, FinderModesChangedSignal):
            self._modes_mask = signal.modes_mask
            logger.debug(
                "finder_modes_changed modes_mask=%s previous_modes_mask=%s",
                signal.modes_mask,
                signal.previous_modes_mask,
            )
            return []

        if isinstance(signal, FinderModeInvalidatedSignal):
            self._modes_mask = None
            logger.debug(
                "finder_mode_invalidated previous_modes_mask=%s", signal.previous_modes_mask
            )
            return []

        if isinstance(signal, FinderUnitsChangedSignal):
            self._remember_units(
                ammo_per_drop=signal.ammo_per_drop,
                probes_per_drop=signal.probes_per_drop,
            )
            logger.debug(
                "finder_units_changed probes_per_drop=%s ammo_per_drop=%s "
                "cached_probes_per_drop=%s cached_ammo_per_drop=%s",
                signal.probes_per_drop,
                signal.ammo_per_drop,
                self._probes_per_drop,
                self._ammo_per_drop,
            )
            return []

        if isinstance(signal, ProbeFiredSignal):
            return self._record_drop(signal)

        if isinstance(signal, FinderHitHintSignal):
            return [self._record_hit_hint(signal)]

        if isinstance(signal, FinderNoResourcesSignal):
            return [self._record_no_resources(signal)]

        return []

    def _record_drop(self, signal: ProbeFiredSignal) -> list[EventBase]:
        if self._probe_signal_is_locked(signal.ts_ms):
            return []

        position = self._position_provider()
        if position is None:
            logger.warning("drop_without_position signal=%s", signal)

        modes_mask = signal.modes_mask if signal.modes_mask is not None else self._modes_mask
        ammo_per_drop, probes_per_drop = self._resolve_drop_units(signal)

        profile = self._profile_provider()
        cost = calculate_drop_cost(
            profile=profile,
            ocr_ammo_per_drop=ammo_per_drop,
            ocr_probes_per_drop=probes_per_drop,
        )
        if cost.ammo.quantity is None and cost.probes.quantity is None:
            logger.warning(
                "drop_without_valid_units signal_ts=%s modes=%s position=%s raw_ammo=%s raw_probes=%s",
                signal.ts_ms,
                modes_mask,
                position,
                signal.ammo_per_drop,
                signal.probes_per_drop,
            )
            return []

        segment_setup = MiningSegmentSetup(
            profile=profile,
            modes_mask=modes_mask,
            ammo_per_drop=ammo_per_drop,
            probes_per_drop=probes_per_drop,
        )
        run_context = (
            self._run_context_provider(signal.ts_ms, segment_setup)
            if self._run_context_provider is not None
            else DropRunContext(run_id=None, segment_id=None)
        )
        event = MiningDropEvent(
            drop_id=self._id_factory(),
            observed_ts_ms=signal.ts_ms,
            position=position,
            modes_mask=modes_mask,
            probes_per_drop=probes_per_drop,
            ammo_per_drop=ammo_per_drop,
            cost=cost,
            drop_radius_m=effective_finder_radius_m(profile) or DEFAULT_DROP_RADIUS_M,
            raw_status_text=signal.raw_status_text,
            run_id=run_context.run_id,
            segment_id=run_context.segment_id,
        )
        self._last_accepted_probe_ts_ms = signal.ts_ms
        self._pending_drop = event
        logger.debug(
            "probe_fired_signal_processed event_type=%s drop_id=%s ts=%s position=%s "
            "modes=%s ammo=%s probes=%s total_tt_mpec=%s total_with_markup_mpec=%s",
            type(event).__name__,
            event.drop_id,
            event.observed_ts_ms,
            event.position,
            event.modes_mask,
            event.ammo_per_drop,
            event.probes_per_drop,
            event.cost.total_tt_mpec,
            event.cost.total_with_markup_mpec,
        )
        return [*run_context.lifecycle_events, event]

    def _probe_signal_is_locked(self, observed_ts_ms: int) -> bool:
        previous_ts_ms = self._last_accepted_probe_ts_ms
        if previous_ts_ms is None or self._config.probe_fired_lock_ms <= 0:
            return False

        elapsed_ms = observed_ts_ms - previous_ts_ms
        if elapsed_ms >= self._config.probe_fired_lock_ms:
            return False

        logger.debug(
            "probe_fired_signal_ignored reason=%s ts=%s previous_ts=%s elapsed_ms=%s lock_ms=%s",
            "stale" if elapsed_ms < 0 else "locked",
            observed_ts_ms,
            previous_ts_ms,
            elapsed_ms,
            self._config.probe_fired_lock_ms,
        )
        return True

    def _resolve_drop_units(self, signal: ProbeFiredSignal) -> tuple[int | None, int | None]:
        remembered = self._remember_units(
            ammo_per_drop=signal.ammo_per_drop,
            probes_per_drop=signal.probes_per_drop,
        )
        if remembered is not None:
            return remembered
        return self._ammo_per_drop, self._probes_per_drop

    def _remember_units(
        self,
        *,
        ammo_per_drop: int | None,
        probes_per_drop: int | None,
    ) -> tuple[int | None, int | None] | None:
        positive_ammo = _positive_unit_or_none(ammo_per_drop)
        positive_probes = _positive_unit_or_none(probes_per_drop)
        if positive_ammo is not None:
            self._ammo_per_drop = positive_ammo
            self._probes_per_drop = None
            return positive_ammo, None
        if positive_probes is not None:
            self._ammo_per_drop = None
            self._probes_per_drop = positive_probes
            return None, positive_probes
        return None

    def _record_hit_hint(self, signal: FinderHitHintSignal) -> MiningHitHintEvent:
        linked_drop = self._linked_pending_drop(signal.ts_ms)
        if linked_drop is None:
            logger.warning(
                "claim_without_drop signal_type=%s ts=%s resource=%r size=%s(%s)",
                type(signal).__name__,
                signal.ts_ms,
                signal.resource_name,
                signal.size_label,
                signal.size_index,
            )
        if linked_drop is not None:
            # TODO: Keep deed/chat claim correlation separate from this pending-drop slot.
            # Finder shows at most one hint, but multi-mode drops may create multiple
            # deed/chat claim signals around the same time.
            self._pending_drop = None

        event = MiningHitHintEvent(
            hit_id=self._id_factory(),
            drop_id=linked_drop.drop_id if linked_drop is not None else None,
            observed_ts_ms=signal.ts_ms,
            position=linked_drop.position if linked_drop is not None else None,
            size_label=signal.size_label,
            size_index=signal.size_index,
            resource_name=signal.resource_name,
            expected_expires_ts_ms=expected_claim_expires_ts_ms(
                observed_ts_ms=signal.ts_ms,
                size_index=signal.size_index,
                size_label=signal.size_label,
            ),
            range_m=signal.range_m,
            depth_m=signal.depth_m,
            raw_status_text=signal.raw_status_text,
            raw_details_text=signal.raw_details_text,
            run_id=linked_drop.run_id if linked_drop is not None else None,
            segment_id=linked_drop.segment_id if linked_drop is not None else None,
        )
        logger.debug(
            "hit_hint_recorded event_type=%s hit_id=%s drop_id=%s ts=%s resource=%r size=%s(%s)",
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
        if linked_drop is None:
            logger.warning(
                "no_resources_without_drop signal_type=%s ts=%s",
                type(signal).__name__,
                signal.ts_ms,
            )
        if linked_drop is not None:
            self._pending_drop = None

        event = MiningNoResourcesEvent(
            drop_id=linked_drop.drop_id if linked_drop is not None else None,
            observed_ts_ms=signal.ts_ms,
            position=linked_drop.position if linked_drop is not None else None,
            raw_status_text=signal.raw_status_text,
            run_id=linked_drop.run_id if linked_drop is not None else None,
            segment_id=linked_drop.segment_id if linked_drop is not None else None,
        )
        logger.debug(
            "no_resources_recorded event_type=%s drop_id=%s ts=%s position=%s",
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
        logger.warning(
            "drop_result_stale drop_id=%s elapsed_ms=%s link_window_ms=%s",
            drop.drop_id,
            elapsed_ms,
            self._config.result_link_window_ms,
        )
        return None


def _none_position_provider() -> WorldPos | None:
    return None


def _positive_unit_or_none(value: int | None) -> int | None:
    if value is None or value <= 0:
        return None
    return value
