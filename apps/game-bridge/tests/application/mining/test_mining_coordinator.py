from __future__ import annotations

import contextlib
from datetime import datetime
from pathlib import Path

from zml_game_bridge.application.mining import (
    MiningCoordinator,
    MiningCoordinatorConfig,
)
from zml_game_bridge.application.mining.claims.commands import (
    IgnoreMiningClaimCommand,
    MarkMiningClaimDepletedCommand,
)
from zml_game_bridge.application.mining.claims.lifecycle import ActiveClaim
from zml_game_bridge.application.mining.segments.session import DropRunContext, MiningSegmentSetup
from zml_game_bridge.domain.mining import MiningMode
from zml_game_bridge.domain.mining_cost import (
    FinderRangeEnhancerLoadout,
    MiningEquipmentProfile,
    MiningToolProfile,
)
from zml_game_bridge.domain.mining_events import (
    MiningClaimCreatedEvent,
    MiningClaimDeedReceivedEvent,
    MiningClaimDepletedEvent,
    MiningClaimIgnoredEvent,
    MiningDropEvent,
    MiningEnhancerBrokeEvent,
    MiningHitHintEvent,
    MiningItemReceivedEvent,
    MiningNoResourcesEvent,
    RunSegmentStartedEvent,
)
from zml_game_bridge.domain.money import Mpec, mpec_to_int
from zml_game_bridge.domain.position import WorldPos
from zml_game_bridge.domain.rate import percent
from zml_game_bridge.inputs.chat.model import ChannelType
from zml_game_bridge.inputs.chat.signals import (
    EnhancerBrokeSignal,
    ItemReceivedSignal,
    ResourceClaimedSignal,
    ResourceDepletedSignal,
)
from zml_game_bridge.inputs.ocr.pipelines.mining_finder.signals import (
    FinderHitHintSignal,
    FinderModesChangedSignal,
    FinderNoResourcesSignal,
    FinderUnitsChangedSignal,
    ProbeFiredSignal,
)
from zml_game_bridge.resources.mining_resources import MiningResourceCatalog


def test_mining_coordinator_records_probe_drop_with_current_units() -> None:
    position = WorldPos(planet_name="Calypso", x=58_890, y=84_639, z=None)
    coordinator = MiningCoordinator(
        profile=MiningEquipmentProfile(
            finder=MiningToolProfile(name="Finder", decay_mpec=Mpec(100), radius_m=55.2),
        ),
        id_factory=_id_factory("drop-1"),
        position_provider=lambda: position,
    )

    coordinator.process_signal(
        FinderUnitsChangedSignal(ts_ms=900, probes_per_drop=None, ammo_per_drop=1_000)
    )
    events = coordinator.process_signal(
        ProbeFiredSignal(
            ts_ms=1_000,
            position=None,
            modes_mask=int(MiningMode.ORE),
            raw_status_text="Sending probe...",
        )
    )

    assert len(events) == 1
    drop = events[0]
    assert isinstance(drop, MiningDropEvent)
    assert drop.drop_id == "drop-1"
    assert drop.observed_ts_ms == 1_000
    assert drop.position == position
    assert drop.modes_mask == int(MiningMode.ORE)
    assert drop.ammo_per_drop == 1_000
    assert drop.probes_per_drop is None
    assert drop.drop_radius_m == 55.2
    assert mpec_to_int(drop.cost.ammo.cost_mpec) == 10_000
    assert drop.cost.ammo.source == "ocr"
    assert mpec_to_int(drop.cost.finder_decay_mpec) == 100
    assert mpec_to_int(drop.cost.finder_enhancer_decay_mpec) == 0
    assert mpec_to_int(drop.cost.total_mpec) == 10_100


def test_mining_coordinator_attaches_active_run_segment_to_drop() -> None:
    segment_started = RunSegmentStartedEvent(
        segment_id="segment-1",
        run_id=7,
        segment_index=1,
        started_ts_ms=1_000,
        setup_hash="hash-1",
        setup_snapshot={"finder": {"name": "Finder"}},
    )
    coordinator = MiningCoordinator(
        id_factory=_id_factory("drop-1"),
        run_context_provider=lambda _ts, _setup: DropRunContext(
            run_id=7,
            segment_id="segment-1",
            lifecycle_events=(segment_started,),
        ),
    )

    events = coordinator.process_signal(
        ProbeFiredSignal(ts_ms=1_000, position=None, modes_mask=1, ammo_per_drop=1_000)
    )

    assert events[0] == segment_started
    drop = events[1]
    assert isinstance(drop, MiningDropEvent)
    assert drop.drop_id == "drop-1"
    assert drop.run_id == 7
    assert drop.segment_id == "segment-1"


def test_mining_coordinator_carries_drop_run_segment_to_claim() -> None:
    coordinator = MiningCoordinator(
        id_factory=_id_factory("drop-1", "hit-1", "claim-1"),
        run_context_provider=lambda _ts, _setup: DropRunContext(
            run_id=7,
            segment_id="segment-1",
        ),
    )
    coordinator.process_signal(
        ProbeFiredSignal(ts_ms=1_000, position=None, modes_mask=1, ammo_per_drop=1_000)
    )

    events = coordinator.process_signal(
        FinderHitHintSignal(
            ts_ms=2_000,
            size_label="Minimal",
            size_index=1,
            resource_name="Lysterium Stone",
        )
    )

    claim = events[1]
    assert isinstance(claim, MiningClaimCreatedEvent)
    assert claim.drop_id == "drop-1"
    assert claim.run_id == 7
    assert claim.segment_id == "segment-1"


def test_mining_coordinator_passes_drop_setup_to_run_segment_context() -> None:
    captured_setups: list[MiningSegmentSetup] = []

    def context_provider(_observed_ts_ms: int, setup: MiningSegmentSetup) -> DropRunContext:
        captured_setups.append(setup)
        return DropRunContext(run_id=7, segment_id="segment-1")

    coordinator = MiningCoordinator(
        id_factory=_id_factory("drop-1"),
        run_context_provider=context_provider,
    )

    coordinator.process_signal(
        FinderModesChangedSignal(
            ts_ms=900,
            modes_mask=int(MiningMode.ORE | MiningMode.ENMATTER),
            previous_modes_mask=None,
        )
    )
    coordinator.process_signal(
        FinderUnitsChangedSignal(ts_ms=950, probes_per_drop=None, ammo_per_drop=1_500)
    )
    coordinator.process_signal(
        ProbeFiredSignal(ts_ms=1_000, position=None, modes_mask=None, ammo_per_drop=None)
    )

    assert len(captured_setups) == 1
    assert captured_setups[0].modes_mask == int(MiningMode.ORE | MiningMode.ENMATTER)
    assert captured_setups[0].ammo_per_drop == 1_500
    assert captured_setups[0].probes_per_drop is None


def test_mining_coordinator_applies_finder_range_enhancer_to_drop_cost_and_radius() -> None:
    coordinator = MiningCoordinator(
        profile=MiningEquipmentProfile(
            finder=MiningToolProfile(name="Finder", decay_mpec=Mpec(1_000), radius_m=55.0),
            finder_range_enhancers=FinderRangeEnhancerLoadout(count=1),
        ),
        id_factory=_id_factory("drop-1"),
    )

    events = coordinator.process_signal(
        ProbeFiredSignal(ts_ms=1_000, position=None, modes_mask=1, ammo_per_drop=1_000)
    )

    drop = events[0]
    assert isinstance(drop, MiningDropEvent)
    assert drop.drop_radius_m == 55.55
    assert mpec_to_int(drop.cost.finder_decay_mpec) == 1_000
    assert mpec_to_int(drop.cost.finder_enhancer_decay_mpec) == 100
    assert mpec_to_int(drop.cost.total_mpec) == 11_100


def test_mining_coordinator_uses_current_modes_when_probe_signal_lacks_modes() -> None:
    coordinator = MiningCoordinator(id_factory=_id_factory("drop-1"))

    coordinator.process_signal(
        FinderModesChangedSignal(
            ts_ms=900,
            modes_mask=int(MiningMode.ORE | MiningMode.ENMATTER),
            previous_modes_mask=None,
        )
    )
    events = coordinator.process_signal(
        ProbeFiredSignal(ts_ms=1_000, position=None, modes_mask=None, ammo_per_drop=1_000)
    )

    drop = events[0]
    assert isinstance(drop, MiningDropEvent)
    assert drop.modes_mask == int(MiningMode.ORE | MiningMode.ENMATTER)


def test_mining_coordinator_prefers_probe_signal_units_over_cached_units() -> None:
    coordinator = MiningCoordinator(id_factory=_id_factory("drop-1"))

    coordinator.process_signal(
        FinderUnitsChangedSignal(ts_ms=900, probes_per_drop=None, ammo_per_drop=500)
    )
    events = coordinator.process_signal(
        ProbeFiredSignal(ts_ms=1_000, position=None, modes_mask=None, ammo_per_drop=1_000)
    )

    drop = events[0]
    assert isinstance(drop, MiningDropEvent)
    assert drop.ammo_per_drop == 1_000
    assert mpec_to_int(drop.cost.total_mpec) == 10_000


def test_mining_coordinator_records_hit_hint_linked_to_recent_drop() -> None:
    position = WorldPos(planet_name="Calypso", x=58_890, y=84_639, z=None)
    coordinator = MiningCoordinator(
        id_factory=_id_factory("drop-1", "hit-1", "claim-1"),
        position_provider=lambda: position,
    )

    coordinator.process_signal(
        ProbeFiredSignal(ts_ms=1_000, position=None, modes_mask=1, ammo_per_drop=1_000)
    )
    events = coordinator.process_signal(
        FinderHitHintSignal(
            ts_ms=5_000,
            size_label="Minimal",
            size_index=1,
            resource_name="Lysterium Stone",
            range_m=51.14,
            depth_m=53.0,
        )
    )

    assert len(events) == 2
    hit = events[0]
    assert isinstance(hit, MiningHitHintEvent)
    assert hit.hit_id == "hit-1"
    assert hit.drop_id == "drop-1"
    assert hit.position == position
    assert hit.resource_name == "Lysterium Stone"
    assert hit.size_label == "Minimal"
    assert hit.size_index == 1
    assert hit.expected_expires_ts_ms == 3_605_000
    assert hit.range_m == 51.14
    assert hit.depth_m == 53.0
    claim = events[1]
    assert isinstance(claim, MiningClaimCreatedEvent)
    assert claim.claim_id == "claim-1"
    assert claim.hit_id == "hit-1"
    assert claim.drop_id == "drop-1"
    assert claim.run_id is None
    assert claim.segment_id is None
    assert claim.position == position
    assert claim.search_radius_m == 55.0
    assert claim.resource_name == "Lysterium Stone"
    assert claim.expected_expires_ts_ms == 3_605_000


def test_mining_coordinator_records_non_expiring_hit_hint() -> None:
    coordinator = MiningCoordinator(id_factory=_id_factory("drop-1", "hit-1", "claim-1"))

    coordinator.process_signal(
        ProbeFiredSignal(ts_ms=1_000, position=None, modes_mask=1, ammo_per_drop=1_000)
    )
    events = coordinator.process_signal(
        FinderHitHintSignal(
            ts_ms=5_000,
            size_label="Rich",
            size_index=23,
            resource_name="Lysterium Stone",
        )
    )

    hit = events[0]
    assert isinstance(hit, MiningHitHintEvent)
    assert hit.expected_expires_ts_ms is None
    claim = events[1]
    assert isinstance(claim, MiningClaimCreatedEvent)
    assert claim.expected_expires_ts_ms is None


def test_mining_coordinator_records_no_resources_linked_to_recent_drop() -> None:
    position = WorldPos(planet_name="Calypso", x=58_890, y=84_639, z=None)
    coordinator = MiningCoordinator(
        id_factory=_id_factory("drop-1"),
        position_provider=lambda: position,
    )

    coordinator.process_signal(
        ProbeFiredSignal(ts_ms=1_000, position=None, modes_mask=1, ammo_per_drop=1_000)
    )
    events = coordinator.process_signal(
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


def test_mining_coordinator_no_resources_closes_pending_drop() -> None:
    coordinator = MiningCoordinator(id_factory=_id_factory("drop-1", "hit-1", "claim-1"))

    coordinator.process_signal(
        ProbeFiredSignal(ts_ms=1_000, position=None, modes_mask=1, ammo_per_drop=1_000)
    )
    coordinator.process_signal(FinderNoResourcesSignal(ts_ms=5_000))
    events = coordinator.process_signal(
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


def test_mining_coordinator_does_not_link_hit_to_stale_drop() -> None:
    coordinator = MiningCoordinator(
        config=MiningCoordinatorConfig(result_link_window_ms=1_000),
        id_factory=_id_factory("drop-1", "hit-1", "claim-1"),
    )

    coordinator.process_signal(
        ProbeFiredSignal(ts_ms=1_000, position=None, modes_mask=1, ammo_per_drop=1_000)
    )
    events = coordinator.process_signal(
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
    claim = events[1]
    assert isinstance(claim, MiningClaimCreatedEvent)
    assert claim.drop_id is None
    assert claim.position is None


def test_mining_coordinator_does_not_link_no_resources_to_stale_drop() -> None:
    coordinator = MiningCoordinator(
        config=MiningCoordinatorConfig(result_link_window_ms=1_000),
        id_factory=_id_factory("drop-1"),
    )

    coordinator.process_signal(
        ProbeFiredSignal(ts_ms=1_000, position=None, modes_mask=1, ammo_per_drop=1_000)
    )
    events = coordinator.process_signal(FinderNoResourcesSignal(ts_ms=3_000))

    no_resources = events[0]
    assert isinstance(no_resources, MiningNoResourcesEvent)
    assert no_resources.drop_id is None
    assert no_resources.position is None


def test_mining_coordinator_records_claim_deed_received_chat_event() -> None:
    coordinator = MiningCoordinator()
    event_dt = datetime(2026, 1, 10, 12, 37, 50)
    received_raw = (
        "2026-01-10 12:37:50 [System] [] You received Mineral Resource Deed x (1) Value: 0.0000 PED"
    )
    claimed_raw = "2026-01-10 12:37:50 [System] [] You have claimed a resource! (Lysterium Stone)"

    assert (
        coordinator.process_signal(
            ItemReceivedSignal(
                event_dt=event_dt,
                channel_type=ChannelType.SYSTEM,
                channel_token="System",
                raw=received_raw,
                item_name="Mineral Resource Deed",
                qty=1,
                value_mpec=Mpec(0),
            )
        )
        == []
    )
    events = coordinator.process_signal(
        ResourceClaimedSignal(
            event_dt=event_dt,
            channel_type=ChannelType.SYSTEM,
            channel_token="System",
            raw=claimed_raw,
            resource_name="Lysterium Stone",
        )
    )

    assert len(events) == 1
    event = events[0]
    assert isinstance(event, MiningClaimDeedReceivedEvent)
    assert event.event_dt == event_dt
    assert event.resource_name == "Lysterium Stone"
    assert event.mining_type == "ore"
    assert event.deed_item_name == "Mineral Resource Deed"
    assert event.qty == 1
    assert event.value_mpec == Mpec(0)
    assert event.raw == f"{received_raw}\n{claimed_raw}"
    assert event.received_raw == received_raw
    assert event.claimed_raw == claimed_raw


def test_mining_coordinator_learns_claim_deed_resource(tmp_path: Path) -> None:
    seed_path = tmp_path / "seed.json"
    user_path = tmp_path / "mining_resources.json"
    seed_path.write_text("{}", encoding="utf-8")
    resource_catalog = MiningResourceCatalog(seed_path=seed_path, user_path=user_path)
    coordinator = MiningCoordinator(resource_catalog=resource_catalog)
    event_dt = datetime(2026, 1, 10, 12, 37, 50)

    coordinator.process_signal(
        ItemReceivedSignal(
            event_dt=event_dt,
            channel_type=ChannelType.SYSTEM,
            channel_token="System",
            raw="deed raw",
            item_name="Mineral Resource Deed",
            qty=1,
            value_mpec=Mpec(0),
        )
    )
    coordinator.process_signal(
        ResourceClaimedSignal(
            event_dt=event_dt,
            channel_type=ChannelType.SYSTEM,
            channel_token="System",
            raw="claimed raw",
            resource_name="Narcanisum Stone",
        )
    )

    learned = resource_catalog.get("Narcanisum Stone")
    assert learned is not None
    assert learned.resource_type == "ore"
    assert learned.source == "learned"
    assert user_path.exists()


def test_mining_coordinator_orders_multiple_pending_claim_deeds() -> None:
    coordinator = MiningCoordinator()
    event_dt = datetime(2026, 1, 10, 12, 37, 50)

    coordinator.process_signal(
        ItemReceivedSignal(
            event_dt=event_dt,
            channel_type=ChannelType.SYSTEM,
            channel_token="System",
            raw="ore deed raw",
            item_name="Mineral Resource Deed",
            qty=1,
            value_mpec=Mpec(0),
        )
    )
    coordinator.process_signal(
        ItemReceivedSignal(
            event_dt=event_dt,
            channel_type=ChannelType.SYSTEM,
            channel_token="System",
            raw="enmatter deed raw",
            item_name="Energy Matter Resource Deed",
            qty=1,
            value_mpec=Mpec(0),
        )
    )

    ore_events = coordinator.process_signal(
        ResourceClaimedSignal(
            event_dt=event_dt,
            channel_type=ChannelType.SYSTEM,
            channel_token="System",
            raw="ore claimed raw",
            resource_name="Gazzurdite Stone",
        )
    )
    enmatter_events = coordinator.process_signal(
        ResourceClaimedSignal(
            event_dt=event_dt,
            channel_type=ChannelType.SYSTEM,
            channel_token="System",
            raw="enmatter claimed raw",
            resource_name="Angelic Grit",
        )
    )

    ore = ore_events[0]
    enmatter = enmatter_events[0]
    assert isinstance(ore, MiningClaimDeedReceivedEvent)
    assert isinstance(enmatter, MiningClaimDeedReceivedEvent)
    assert ore.mining_type == "ore"
    assert ore.resource_name == "Gazzurdite Stone"
    assert enmatter.mining_type == "enmatter"
    assert enmatter.resource_name == "Angelic Grit"


def test_mining_coordinator_ignores_unpaired_resource_claimed_chat_signal() -> None:
    coordinator = MiningCoordinator()
    event_dt = datetime(2026, 1, 10, 12, 37, 50)

    events = coordinator.process_signal(
        ResourceClaimedSignal(
            event_dt=event_dt,
            channel_type=ChannelType.SYSTEM,
            channel_token="System",
            raw="2026-01-10 12:37:50 [System] [] You have claimed a resource! (Lysterium Stone)",
            resource_name="Lysterium Stone",
        )
    )

    assert events == []


def test_mining_coordinator_expires_stale_pending_claim_deed() -> None:
    coordinator = MiningCoordinator()
    deed_dt = datetime(2026, 1, 10, 12, 37, 50)
    claimed_dt = datetime(2026, 1, 10, 12, 38, 5)

    coordinator.process_signal(
        ItemReceivedSignal(
            event_dt=deed_dt,
            channel_type=ChannelType.SYSTEM,
            channel_token="System",
            raw="2026-01-10 12:37:50 [System] [] You received Mineral Resource Deed x (1) Value: 0 PED",
            item_name="Mineral Resource Deed",
            qty=1,
            value_mpec=Mpec(0),
        )
    )
    events = coordinator.process_signal(
        ResourceClaimedSignal(
            event_dt=claimed_dt,
            channel_type=ChannelType.SYSTEM,
            channel_token="System",
            raw="2026-01-10 12:38:05 [System] [] You have claimed a resource! (Lysterium Stone)",
            resource_name="Lysterium Stone",
        )
    )

    assert events == []


def test_mining_coordinator_defers_resource_depleted_until_claim_lifecycle_can_link_claim() -> None:
    coordinator = MiningCoordinator()
    event_dt = datetime(2026, 1, 10, 12, 37, 50)

    events = coordinator.process_signal(
        ResourceDepletedSignal(
            event_dt=event_dt,
            channel_type=ChannelType.SYSTEM,
            channel_token="System",
            raw="2026-01-10 12:37:50 [System] [] This resource is depleted",
        )
    )

    assert events == []


def test_mining_coordinator_depletes_nearest_active_claim() -> None:
    drop_position = WorldPos(planet_name="Calypso", x=58_890, y=84_639, z=None)
    current_position = WorldPos(planet_name="Calypso", x=58_894, y=84_642, z=None)
    coordinator = MiningCoordinator(
        id_factory=_id_factory("drop-1", "hit-1", "claim-1"),
        position_provider=_position_provider(drop_position, current_position),
    )
    event_dt = datetime(2026, 1, 10, 12, 37, 50)

    coordinator.process_signal(
        ProbeFiredSignal(
            ts_ms=1_000,
            position=None,
            modes_mask=1,
            ammo_per_drop=1_000,
        )
    )
    coordinator.process_signal(
        FinderHitHintSignal(
            ts_ms=5_000,
            size_label="Minimal",
            size_index=1,
            resource_name="Lysterium Stone",
        )
    )
    events = coordinator.process_signal(
        ResourceDepletedSignal(
            event_dt=event_dt,
            channel_type=ChannelType.SYSTEM,
            channel_token="System",
            raw="2026-01-10 12:37:50 [System] [] This resource is depleted",
        )
    )

    assert len(events) == 1
    event = events[0]
    assert isinstance(event, MiningClaimDepletedEvent)
    assert event.claim_id == "claim-1"
    assert event.drop_id == "drop-1"
    assert event.hit_id == "hit-1"
    assert event.event_dt == event_dt
    assert event.position == current_position
    assert round(event.distance_m, 2) == 5.0


def test_mining_coordinator_does_not_deplete_far_claim() -> None:
    drop_position = WorldPos(planet_name="Calypso", x=58_890, y=84_639, z=None)
    far_position = WorldPos(planet_name="Calypso", x=59_500, y=85_500, z=None)
    coordinator = MiningCoordinator(
        config=MiningCoordinatorConfig(claim_depletion_link_max_distance_m=20.0),
        id_factory=_id_factory("drop-1", "hit-1", "claim-1"),
        position_provider=_position_provider(drop_position, far_position),
    )

    coordinator.process_signal(
        ProbeFiredSignal(
            ts_ms=1_000,
            position=None,
            modes_mask=1,
            ammo_per_drop=1_000,
        )
    )
    coordinator.process_signal(
        FinderHitHintSignal(
            ts_ms=5_000,
            size_label="Minimal",
            size_index=1,
            resource_name="Lysterium Stone",
        )
    )
    events = coordinator.process_signal(
        ResourceDepletedSignal(
            event_dt=datetime(2026, 1, 10, 12, 37, 50),
            channel_type=ChannelType.SYSTEM,
            channel_token="System",
            raw="2026-01-10 12:37:50 [System] [] This resource is depleted",
        )
    )

    assert events == []


def test_mining_coordinator_depletes_restored_active_claim() -> None:
    current_position = WorldPos(planet_name="Calypso", x=58_894, y=84_642, z=None)
    coordinator = MiningCoordinator(position_provider=lambda: current_position)
    coordinator.restore_active_claims(
        [
            ActiveClaim(
                claim_id="claim-1",
                drop_id="drop-1",
                hit_id="hit-1",
                run_id=7,
                segment_id="segment-1",
                position=WorldPos(planet_name="Calypso", x=58_890, y=84_639, z=None),
                search_radius_m=55.0,
            )
        ]
    )
    event_dt = datetime(2026, 1, 10, 12, 37, 50)

    events = coordinator.process_signal(
        ResourceDepletedSignal(
            event_dt=event_dt,
            channel_type=ChannelType.SYSTEM,
            channel_token="System",
            raw="2026-01-10 12:37:50 [System] [] This resource is depleted",
        )
    )

    assert len(events) == 1
    event = events[0]
    assert isinstance(event, MiningClaimDepletedEvent)
    assert event.claim_id == "claim-1"
    assert event.drop_id == "drop-1"
    assert event.hit_id == "hit-1"
    assert event.run_id == 7
    assert event.segment_id == "segment-1"


def test_mining_coordinator_ignores_active_claim_by_command() -> None:
    coordinator = MiningCoordinator()
    coordinator.restore_active_claims(
        [
            ActiveClaim(
                claim_id="claim-1",
                drop_id="drop-1",
                hit_id="hit-1",
                run_id=7,
                segment_id="segment-1",
                position=WorldPos(planet_name="Calypso", x=58_890, y=84_639, z=None),
                search_radius_m=55.0,
            )
        ]
    )

    result = coordinator.process_command(
        IgnoreMiningClaimCommand(
            claim_id="claim-1",
            ignored_ts_ms=2_500,
            reason="manual map action",
            drop_id=None,
            hit_id=None,
            run_id=None,
            segment_id=None,
        )
    )

    assert result.value is None
    assert len(result.events) == 1
    event = result.events[0]
    assert isinstance(event, MiningClaimIgnoredEvent)
    assert event.claim_id == "claim-1"
    assert event.drop_id == "drop-1"
    assert event.hit_id == "hit-1"
    assert event.run_id == 7
    assert event.segment_id == "segment-1"


def test_mining_coordinator_marks_active_claim_depleted_by_command() -> None:
    coordinator = MiningCoordinator()
    coordinator.restore_active_claims(
        [
            ActiveClaim(
                claim_id="claim-1",
                drop_id="drop-1",
                hit_id="hit-1",
                run_id=7,
                segment_id="segment-1",
                position=WorldPos(planet_name="Calypso", x=58_890, y=84_639, z=None),
                search_radius_m=55.0,
            )
        ]
    )
    event_dt = datetime(2026, 1, 10, 12, 37, 50)
    position = WorldPos(planet_name="Calypso", x=58_890, y=84_639, z=None)

    result = coordinator.process_command(
        MarkMiningClaimDepletedCommand(
            claim_id="claim-1",
            event_dt=event_dt,
            position=position,
            distance_m=0.0,
            raw="manual map action",
            drop_id=None,
            hit_id=None,
            run_id=None,
            segment_id=None,
        )
    )

    assert result.value is None
    assert len(result.events) == 1
    event = result.events[0]
    assert isinstance(event, MiningClaimDepletedEvent)
    assert event.claim_id == "claim-1"
    assert event.drop_id == "drop-1"
    assert event.hit_id == "hit-1"
    assert event.run_id == 7
    assert event.segment_id == "segment-1"
    assert event.position == position


def test_mining_coordinator_records_item_received_chat_event() -> None:
    coordinator = MiningCoordinator()
    event_dt = datetime(2026, 1, 10, 12, 37, 50)

    events = coordinator.process_signal(
        ItemReceivedSignal(
            event_dt=event_dt,
            channel_type=ChannelType.SYSTEM,
            channel_token="System",
            raw="2026-01-10 12:37:50 [System] [] You received Blue Crystal x (8) Value: 0.1600 PED",
            item_name="Blue Crystal",
            qty=8,
            value_mpec=Mpec(16_000),
        )
    )

    assert len(events) == 1
    event = events[0]
    assert isinstance(event, MiningItemReceivedEvent)
    assert event.event_dt == event_dt
    assert event.item_name == "Blue Crystal"
    assert event.qty == 8
    assert event.value_mpec == Mpec(16_000)
    assert event.extraction_cost_mpec is None
    assert event.run_id is None


def test_mining_coordinator_attaches_active_run_to_item_received_chat_event() -> None:
    coordinator = MiningCoordinator(run_id_provider=lambda: 7)
    event_dt = datetime(2026, 1, 10, 12, 37, 50)

    events = coordinator.process_signal(
        ItemReceivedSignal(
            event_dt=event_dt,
            channel_type=ChannelType.SYSTEM,
            channel_token="System",
            raw="2026-01-10 12:37:50 [System] [] You received Blue Crystal x (8) Value: 0.1600 PED",
            item_name="Blue Crystal",
            qty=8,
            value_mpec=Mpec(16_000),
        )
    )

    event = events[0]
    assert isinstance(event, MiningItemReceivedEvent)
    assert event.run_id == 7


def test_mining_coordinator_adds_extractor_cost_to_item_received_event() -> None:
    coordinator = MiningCoordinator(
        profile=MiningEquipmentProfile(
            finder=MiningToolProfile(name="Finder", decay_mpec=Mpec(0)),
            extractor=MiningToolProfile(
                name="Extractor", decay_mpec=Mpec(100), markup=percent("125")
            ),
        )
    )
    event_dt = datetime(2026, 1, 10, 12, 37, 50)

    events = coordinator.process_signal(
        ItemReceivedSignal(
            event_dt=event_dt,
            channel_type=ChannelType.SYSTEM,
            channel_token="System",
            raw="2026-01-10 12:37:50 [System] [] You received Blue Crystal x (8) Value: 0.1600 PED",
            item_name="Blue Crystal",
            qty=8,
            value_mpec=Mpec(16_000),
        )
    )

    event = events[0]
    assert isinstance(event, MiningItemReceivedEvent)
    assert event.extraction_cost_mpec == Mpec(125)


def test_mining_coordinator_ignores_unknown_item_received_chat_event(tmp_path: Path) -> None:
    seed_path = tmp_path / "seed.json"
    seed_path.write_text("{}", encoding="utf-8")
    coordinator = MiningCoordinator(
        resource_catalog=MiningResourceCatalog(seed_path=seed_path, user_path=None)
    )
    event_dt = datetime(2026, 1, 10, 12, 37, 50)

    events = coordinator.process_signal(
        ItemReceivedSignal(
            event_dt=event_dt,
            channel_type=ChannelType.SYSTEM,
            channel_token="System",
            raw="2026-01-10 12:37:50 [System] [] You received Random Item x (1) Value: 0.0100 PED",
            item_name="Random Item",
            qty=1,
            value_mpec=Mpec(1_000),
        )
    )

    assert events == []


def test_mining_coordinator_records_enhancer_broke_chat_event() -> None:
    coordinator = MiningCoordinator()
    event_dt = datetime(2026, 1, 10, 12, 37, 50)

    events = coordinator.process_signal(
        EnhancerBrokeSignal(
            event_dt=event_dt,
            channel_type=ChannelType.SYSTEM,
            channel_token="System",
            raw=(
                "2026-01-10 12:37:50 [System] [] Your enhancer T2 Mining Excavator Speed"
                " Enhancer on your Genesis Star Excavator broke. You have 413 enhancers"
                " remaining on the item."
            ),
            enhancer_name="T2 Mining Excavator Speed Enhancer",
            item_name="Genesis Star Excavator",
            remaining=413,
        )
    )

    assert len(events) == 1
    event = events[0]
    assert isinstance(event, MiningEnhancerBrokeEvent)
    assert event.event_dt == event_dt
    assert event.enhancer_name == "T2 Mining Excavator Speed Enhancer"
    assert event.item_name == "Genesis Star Excavator"
    assert event.remaining == 413


def _id_factory(*ids: str):
    iterator = iter(ids)

    def next_id() -> str:
        return next(iterator)

    return next_id


def _position_provider(*positions: WorldPos):
    iterator = iter(positions)
    last_position: WorldPos | None = None

    def next_position() -> WorldPos | None:
        nonlocal last_position
        with contextlib.suppress(StopIteration):
            last_position = next(iterator)
        return last_position

    return next_position
