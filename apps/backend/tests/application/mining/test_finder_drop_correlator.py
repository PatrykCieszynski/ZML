from __future__ import annotations

from zml_backend.application.mining.drops.finder_correlator import FinderDropCorrelator
from zml_backend.application.mining.segments.session import DropRunContext, MiningSegmentSetup
from zml_backend.application.mining.settings import MiningCoordinatorConfig
from zml_backend.application.mining.signals.finder import (
    FinderModeInvalidatedSignal,
    FinderModesChangedSignal,
    ProbeFiredSignal,
)
from zml_backend.domain.mining_cost import MiningEquipmentProfile, MiningToolProfile
from zml_backend.domain.mining_events import MiningDropEvent
from zml_backend.domain.money import Mpec


def test_mode_invalidation_keeps_last_known_mode_for_next_drop() -> None:
    seen_setups: list[MiningSegmentSetup] = []

    def context_for_drop(_observed_ts_ms: int, setup: MiningSegmentSetup) -> DropRunContext:
        seen_setups.append(setup)
        return DropRunContext(run_id=1, segment_id="segment-1")

    correlator = FinderDropCorrelator(
        profile_provider=_profile,
        run_context_provider=context_for_drop,
        config=MiningCoordinatorConfig(probe_fired_lock_ms=0),
        id_factory=lambda: "drop-1",
    )

    correlator.process_signal(
        FinderModesChangedSignal(ts_ms=1_000, modes_mask=1, previous_modes_mask=None)
    )
    correlator.process_signal(FinderModeInvalidatedSignal(ts_ms=1_500, previous_modes_mask=1))
    events = correlator.process_signal(
        ProbeFiredSignal(
            ts_ms=2_000,
            position=None,
            modes_mask=None,
            ammo_per_drop=1_000,
        )
    )

    drop = next(event for event in events if isinstance(event, MiningDropEvent))
    assert drop.modes_mask == 1
    assert seen_setups[-1].modes_mask == 1


def test_mode_invalidation_can_restore_previous_mode_when_cache_is_empty() -> None:
    seen_setups: list[MiningSegmentSetup] = []

    def context_for_drop(_observed_ts_ms: int, setup: MiningSegmentSetup) -> DropRunContext:
        seen_setups.append(setup)
        return DropRunContext(run_id=1, segment_id="segment-1")

    correlator = FinderDropCorrelator(
        profile_provider=_profile,
        run_context_provider=context_for_drop,
        config=MiningCoordinatorConfig(probe_fired_lock_ms=0),
        id_factory=lambda: "drop-1",
    )

    correlator.process_signal(FinderModeInvalidatedSignal(ts_ms=1_500, previous_modes_mask=3))
    correlator.process_signal(
        ProbeFiredSignal(
            ts_ms=2_000,
            position=None,
            modes_mask=None,
            ammo_per_drop=1_000,
        )
    )

    assert seen_setups[-1].modes_mask == 3


def _profile() -> MiningEquipmentProfile:
    return MiningEquipmentProfile(
        finder=MiningToolProfile(
            name="Rookie",
            decay_mpec=Mpec(100),
            radius_m=55.0,
        )
    )
