from __future__ import annotations

from zml_game_bridge.domain.mining import MiningMode
from zml_game_bridge.domain.mining_cost import MiningEquipmentProfile, MiningToolProfile
from zml_game_bridge.domain.mining_events import (
    MiningDropEvent,
    MiningHitHintEvent,
    MiningNoResourcesEvent,
)
from zml_game_bridge.domain.money import Mpec, mpec_to_int
from zml_game_bridge.domain.position import WorldPos
from zml_game_bridge.inputs.ocr.signals import (
    FinderHitHintSignal,
    FinderModesChangedSignal,
    FinderNoResourcesSignal,
    FinderUnitsChangedSignal,
    ProbeFiredSignal,
)
from zml_game_bridge.runtime.mining_runtime_coordinator import (
    MiningRuntimeCoordinator,
    MiningRuntimeCoordinatorConfig,
)


def test_mining_runtime_coordinator_records_probe_drop_with_current_units() -> None:
    coordinator = MiningRuntimeCoordinator(
        profile=MiningEquipmentProfile(
            finder=MiningToolProfile(name="Finder", decay_mpec=Mpec(100)),
        ),
        id_factory=_id_factory("drop-1"),
    )

    coordinator.process(
        FinderUnitsChangedSignal(ts_ms=900, probes_per_drop=None, ammo_per_drop=1_000)
    )
    events = coordinator.process(
        ProbeFiredSignal(
            ts_ms=1_000,
            position=WorldPos(planet_name="Calypso", x=58_890, y=84_639, z=None),
            modes_mask=int(MiningMode.ORE),
            raw_status_text="Sending probe...",
        )
    )

    assert len(events) == 1
    drop = events[0]
    assert isinstance(drop, MiningDropEvent)
    assert drop.drop_id == "drop-1"
    assert drop.observed_ts_ms == 1_000
    assert drop.position == WorldPos(planet_name="Calypso", x=58_890, y=84_639, z=None)
    assert drop.modes_mask == int(MiningMode.ORE)
    assert drop.ammo_per_drop == 1_000
    assert drop.probes_per_drop is None
    assert mpec_to_int(drop.cost.ammo.cost_mpec) == 10_000
    assert drop.cost.ammo.source == "ocr"
    assert mpec_to_int(drop.cost.finder_decay_mpec) == 100
    assert mpec_to_int(drop.cost.total_mpec) == 10_100


def test_mining_runtime_coordinator_uses_current_modes_when_probe_signal_lacks_modes() -> None:
    coordinator = MiningRuntimeCoordinator(id_factory=_id_factory("drop-1"))

    coordinator.process(
        FinderModesChangedSignal(
            ts_ms=900,
            modes_mask=int(MiningMode.ORE | MiningMode.ENMATTER),
            previous_modes_mask=None,
        )
    )
    events = coordinator.process(
        ProbeFiredSignal(ts_ms=1_000, position=None, modes_mask=None, ammo_per_drop=1_000)
    )

    drop = events[0]
    assert isinstance(drop, MiningDropEvent)
    assert drop.modes_mask == int(MiningMode.ORE | MiningMode.ENMATTER)


def test_mining_runtime_coordinator_prefers_probe_signal_units_over_cached_units() -> None:
    coordinator = MiningRuntimeCoordinator(id_factory=_id_factory("drop-1"))

    coordinator.process(
        FinderUnitsChangedSignal(ts_ms=900, probes_per_drop=None, ammo_per_drop=500)
    )
    events = coordinator.process(
        ProbeFiredSignal(ts_ms=1_000, position=None, modes_mask=None, ammo_per_drop=1_000)
    )

    drop = events[0]
    assert isinstance(drop, MiningDropEvent)
    assert drop.ammo_per_drop == 1_000
    assert mpec_to_int(drop.cost.total_mpec) == 10_000


def test_mining_runtime_coordinator_records_hit_hint_linked_to_recent_drop() -> None:
    position = WorldPos(planet_name="Calypso", x=58_890, y=84_639, z=None)
    coordinator = MiningRuntimeCoordinator(id_factory=_id_factory("drop-1", "hit-1"))

    coordinator.process(
        ProbeFiredSignal(ts_ms=1_000, position=position, modes_mask=1, ammo_per_drop=1_000)
    )
    events = coordinator.process(
        FinderHitHintSignal(
            ts_ms=5_000,
            size_label="Minimal",
            size_index=1,
            resource_name="Lysterium Stone",
            range_m=51.14,
            depth_m=53.0,
        )
    )

    assert len(events) == 1
    hit = events[0]
    assert isinstance(hit, MiningHitHintEvent)
    assert hit.hit_id == "hit-1"
    assert hit.drop_id == "drop-1"
    assert hit.position == position
    assert hit.resource_name == "Lysterium Stone"
    assert hit.size_label == "Minimal"
    assert hit.size_index == 1
    assert hit.range_m == 51.14
    assert hit.depth_m == 53.0


def test_mining_runtime_coordinator_records_no_resources_linked_to_recent_drop() -> None:
    position = WorldPos(planet_name="Calypso", x=58_890, y=84_639, z=None)
    coordinator = MiningRuntimeCoordinator(id_factory=_id_factory("drop-1"))

    coordinator.process(
        ProbeFiredSignal(ts_ms=1_000, position=position, modes_mask=1, ammo_per_drop=1_000)
    )
    events = coordinator.process(
        FinderNoResourcesSignal(
            ts_ms=5_000,
            raw_status_text="No resources found. Try again\nsomewhere else-",
        )
    )

    assert len(events) == 1
    no_resources = events[0]
    assert isinstance(no_resources, MiningNoResourcesEvent)
    assert no_resources.drop_id == "drop-1"
    assert no_resources.position == position
    assert no_resources.raw_status_text == "No resources found. Try again\nsomewhere else-"


def test_mining_runtime_coordinator_no_resources_closes_pending_drop() -> None:
    coordinator = MiningRuntimeCoordinator(id_factory=_id_factory("drop-1", "hit-1"))

    coordinator.process(
        ProbeFiredSignal(ts_ms=1_000, position=None, modes_mask=1, ammo_per_drop=1_000)
    )
    coordinator.process(FinderNoResourcesSignal(ts_ms=5_000))
    events = coordinator.process(
        FinderHitHintSignal(
            ts_ms=6_000,
            size_label="Minimal",
            size_index=1,
            resource_name="Lysterium Stone",
        )
    )

    hit = events[0]
    assert isinstance(hit, MiningHitHintEvent)
    assert hit.drop_id is None


def test_mining_runtime_coordinator_does_not_link_hit_to_stale_drop() -> None:
    coordinator = MiningRuntimeCoordinator(
        config=MiningRuntimeCoordinatorConfig(result_link_window_ms=1_000),
        id_factory=_id_factory("drop-1", "hit-1"),
    )

    coordinator.process(
        ProbeFiredSignal(ts_ms=1_000, position=None, modes_mask=1, ammo_per_drop=1_000)
    )
    events = coordinator.process(
        FinderHitHintSignal(
            ts_ms=3_000,
            size_label="Minimal",
            size_index=1,
            resource_name="Lysterium Stone",
        )
    )

    hit = events[0]
    assert isinstance(hit, MiningHitHintEvent)
    assert hit.drop_id is None
    assert hit.position is None


def test_mining_runtime_coordinator_does_not_link_no_resources_to_stale_drop() -> None:
    coordinator = MiningRuntimeCoordinator(
        config=MiningRuntimeCoordinatorConfig(result_link_window_ms=1_000),
        id_factory=_id_factory("drop-1"),
    )

    coordinator.process(
        ProbeFiredSignal(ts_ms=1_000, position=None, modes_mask=1, ammo_per_drop=1_000)
    )
    events = coordinator.process(FinderNoResourcesSignal(ts_ms=3_000))

    no_resources = events[0]
    assert isinstance(no_resources, MiningNoResourcesEvent)
    assert no_resources.drop_id is None
    assert no_resources.position is None


def _id_factory(*ids: str):
    iterator = iter(ids)

    def next_id() -> str:
        return next(iterator)

    return next_id
