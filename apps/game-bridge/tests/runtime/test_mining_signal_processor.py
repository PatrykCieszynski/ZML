from __future__ import annotations

from zml_game_bridge.domain.mining import MiningMode
from zml_game_bridge.domain.mining_cost import MiningEquipmentProfile, MiningToolProfile
from zml_game_bridge.domain.mining_events import MiningDropRecorded, MiningPreclaimDetected
from zml_game_bridge.domain.money import Mpec, mpec_to_int
from zml_game_bridge.domain.position import WorldPos
from zml_game_bridge.inputs.ocr.signals import (
    FinderHitHint,
    FinderModesChanged,
    FinderUnitsChanged,
    ProbeFired,
)
from zml_game_bridge.runtime.mining_signal_processor import (
    MiningSignalProcessor,
    MiningSignalProcessorConfig,
)


def test_mining_signal_processor_records_probe_drop_with_current_units() -> None:
    processor = MiningSignalProcessor(
        profile=MiningEquipmentProfile(
            finder=MiningToolProfile(name="Finder", decay_mpec=Mpec(100)),
        )
    )

    processor.process(
        FinderUnitsChanged(ts_ms=900, probes_per_drop=None, ammo_per_drop=1_000)
    )
    events = processor.process(
        ProbeFired(
            ts_ms=1_000,
            position=WorldPos(planet_name="Calypso", x=58_890, y=84_639, z=None),
            modes_mask=int(MiningMode.ORE),
            raw_status_text="Sending probe...",
        )
    )

    assert len(events) == 1
    drop = events[0]
    assert isinstance(drop, MiningDropRecorded)
    assert drop.observed_ts_ms == 1_000
    assert drop.position == WorldPos(planet_name="Calypso", x=58_890, y=84_639, z=None)
    assert drop.modes_mask == int(MiningMode.ORE)
    assert drop.ammo_per_drop == 1_000
    assert drop.probes_per_drop is None
    assert mpec_to_int(drop.cost.ammo.cost_mpec) == 10_000
    assert drop.cost.ammo.source == "ocr"
    assert mpec_to_int(drop.cost.finder_decay_mpec) == 100
    assert mpec_to_int(drop.cost.total_mpec) == 10_100


def test_mining_signal_processor_uses_current_modes_when_probe_signal_lacks_modes() -> None:
    processor = MiningSignalProcessor()

    processor.process(
        FinderModesChanged(
            ts_ms=900,
            modes_mask=int(MiningMode.ORE | MiningMode.ENMATTER),
            previous_modes_mask=None,
        )
    )
    events = processor.process(
        ProbeFired(ts_ms=1_000, position=None, modes_mask=None, ammo_per_drop=1_000)
    )

    drop = events[0]
    assert isinstance(drop, MiningDropRecorded)
    assert drop.modes_mask == int(MiningMode.ORE | MiningMode.ENMATTER)


def test_mining_signal_processor_prefers_probe_signal_units_over_cached_units() -> None:
    processor = MiningSignalProcessor()

    processor.process(
        FinderUnitsChanged(ts_ms=900, probes_per_drop=None, ammo_per_drop=500)
    )
    events = processor.process(
        ProbeFired(ts_ms=1_000, position=None, modes_mask=None, ammo_per_drop=1_000)
    )

    drop = events[0]
    assert isinstance(drop, MiningDropRecorded)
    assert drop.ammo_per_drop == 1_000
    assert mpec_to_int(drop.cost.total_mpec) == 10_000


def test_mining_signal_processor_records_preclaim_linked_to_recent_drop() -> None:
    position = WorldPos(planet_name="Calypso", x=58_890, y=84_639, z=None)
    processor = MiningSignalProcessor()

    processor.process(
        ProbeFired(ts_ms=1_000, position=position, modes_mask=1, ammo_per_drop=1_000)
    )
    events = processor.process(
        FinderHitHint(
            ts_ms=5_000,
            size_label="Minimal",
            size_index=1,
            resource_name="Lysterium Stone",
            range_m=51.14,
            depth_m=53.0,
        )
    )

    assert len(events) == 1
    preclaim = events[0]
    assert isinstance(preclaim, MiningPreclaimDetected)
    assert preclaim.drop_observed_ts_ms == 1_000
    assert preclaim.position == position
    assert preclaim.resource_name == "Lysterium Stone"
    assert preclaim.size_label == "Minimal"
    assert preclaim.size_index == 1
    assert preclaim.range_m == 51.14
    assert preclaim.depth_m == 53.0


def test_mining_signal_processor_does_not_link_preclaim_to_stale_drop() -> None:
    processor = MiningSignalProcessor(
        config=MiningSignalProcessorConfig(preclaim_link_window_ms=1_000)
    )

    processor.process(
        ProbeFired(ts_ms=1_000, position=None, modes_mask=1, ammo_per_drop=1_000)
    )
    events = processor.process(
        FinderHitHint(
            ts_ms=3_000,
            size_label="Minimal",
            size_index=1,
            resource_name="Lysterium Stone",
        )
    )

    preclaim = events[0]
    assert isinstance(preclaim, MiningPreclaimDetected)
    assert preclaim.drop_observed_ts_ms is None
    assert preclaim.position is None
