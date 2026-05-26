from __future__ import annotations

from pathlib import Path

from zml_game_bridge.application.mining.segments.session import (
    MiningSegmentSetup,
    RunSessionService,
)
from zml_game_bridge.domain.mining_cost import MiningEquipmentProfile, MiningToolProfile
from zml_game_bridge.domain.mining_events import RunSegmentEndedEvent, RunSegmentStartedEvent
from zml_game_bridge.domain.money import Mpec
from zml_game_bridge.persistence.run_state import RunState
from zml_game_bridge.persistence.runs import RunSegmentStore
from zml_game_bridge.persistence.schema import ensure_schema
from zml_game_bridge.persistence.sqlite import open_sqlite


def test_run_session_starts_segment_on_first_drop(tmp_path: Path) -> None:
    db_path = tmp_path / "run-session.sqlite3"
    _create_active_run(db_path)
    service = RunSessionService(db_path=db_path, id_factory=_id_factory("segment-1"))

    context = service.context_for_drop(observed_ts_ms=1_000, setup=_setup("Finder A"))

    assert context.run_id == 1
    assert context.segment_id == "segment-1"
    assert len(context.lifecycle_events) == 1
    started = context.lifecycle_events[0]
    assert isinstance(started, RunSegmentStartedEvent)
    assert started.segment_id == "segment-1"
    assert started.run_id == 1
    assert started.segment_index == 1
    assert started.started_ts_ms == 1_000
    assert started.setup_snapshot["finder"] == {
        "name": "Finder A",
        "decay_mpec": 100,
        "markup_ppm": 1_000_000,
        "radius_m": 55.0,
    }
    assert started.setup_snapshot["modes_mask"] == 1
    assert started.setup_snapshot["ammo_per_drop"] == 1_000
    assert started.setup_snapshot["probes_per_drop"] is None


def test_run_session_reuses_segment_until_setup_changes(tmp_path: Path) -> None:
    db_path = tmp_path / "run-session.sqlite3"
    _create_active_run(db_path)
    service = RunSessionService(db_path=db_path, id_factory=_id_factory("segment-1", "segment-2"))

    first = service.context_for_drop(observed_ts_ms=1_000, setup=_setup("Finder A"))
    second = service.context_for_drop(observed_ts_ms=2_000, setup=_setup("Finder A"))
    third = service.context_for_drop(observed_ts_ms=3_000, setup=_setup("Finder B"))

    assert first.segment_id == "segment-1"
    assert second.segment_id == "segment-1"
    assert second.lifecycle_events == ()
    assert third.segment_id == "segment-2"
    assert len(third.lifecycle_events) == 2
    ended = third.lifecycle_events[0]
    started = third.lifecycle_events[1]
    assert isinstance(ended, RunSegmentEndedEvent)
    assert ended.segment_id == "segment-1"
    assert ended.reason == "setup_changed"
    assert isinstance(started, RunSegmentStartedEvent)
    assert started.segment_id == "segment-2"
    assert started.segment_index == 2


def test_run_session_starts_new_segment_when_drop_modes_change(tmp_path: Path) -> None:
    db_path = tmp_path / "run-session.sqlite3"
    _create_active_run(db_path)
    service = RunSessionService(db_path=db_path, id_factory=_id_factory("segment-1", "segment-2"))

    first = service.context_for_drop(observed_ts_ms=1_000, setup=_setup("Finder A", modes_mask=1))
    second = service.context_for_drop(observed_ts_ms=2_000, setup=_setup("Finder A", modes_mask=3))

    assert first.segment_id == "segment-1"
    assert second.segment_id == "segment-2"
    assert len(second.lifecycle_events) == 2
    started = second.lifecycle_events[1]
    assert isinstance(started, RunSegmentStartedEvent)
    assert started.setup_snapshot["modes_mask"] == 3


def test_run_session_starts_new_segment_when_drop_units_change(tmp_path: Path) -> None:
    db_path = tmp_path / "run-session.sqlite3"
    _create_active_run(db_path)
    service = RunSessionService(db_path=db_path, id_factory=_id_factory("segment-1", "segment-2"))

    first = service.context_for_drop(
        observed_ts_ms=1_000,
        setup=_setup("Finder A", ammo_per_drop=1_000),
    )
    second = service.context_for_drop(
        observed_ts_ms=2_000,
        setup=_setup("Finder A", ammo_per_drop=2_000),
    )

    assert first.segment_id == "segment-1"
    assert second.segment_id == "segment-2"
    assert len(second.lifecycle_events) == 2
    started = second.lifecycle_events[1]
    assert isinstance(started, RunSegmentStartedEvent)
    assert started.setup_snapshot["ammo_per_drop"] == 2_000


def test_run_session_starts_new_segment_when_probe_count_changes(tmp_path: Path) -> None:
    db_path = tmp_path / "run-session.sqlite3"
    _create_active_run(db_path)
    service = RunSessionService(db_path=db_path, id_factory=_id_factory("segment-1", "segment-2"))

    first = service.context_for_drop(
        observed_ts_ms=1_000,
        setup=_setup("Finder A", ammo_per_drop=None, probes_per_drop=1),
    )
    second = service.context_for_drop(
        observed_ts_ms=2_000,
        setup=_setup("Finder A", ammo_per_drop=None, probes_per_drop=2),
    )

    assert first.segment_id == "segment-1"
    assert second.segment_id == "segment-2"
    assert len(second.lifecycle_events) == 2
    started = second.lifecycle_events[1]
    assert isinstance(started, RunSegmentStartedEvent)
    assert started.setup_snapshot["probes_per_drop"] == 2


def test_run_session_does_not_split_segment_when_only_extractor_changes(tmp_path: Path) -> None:
    db_path = tmp_path / "run-session.sqlite3"
    _create_active_run(db_path)
    service = RunSessionService(db_path=db_path, id_factory=_id_factory("segment-1"))

    first = service.context_for_drop(
        observed_ts_ms=1_000,
        setup=_setup("Finder A", extractor_name="Extractor A"),
    )
    second = service.context_for_drop(
        observed_ts_ms=2_000,
        setup=_setup("Finder A", extractor_name="Extractor B"),
    )

    assert first.segment_id == "segment-1"
    assert second.segment_id == "segment-1"
    assert second.lifecycle_events == ()


def test_run_session_reuses_persisted_active_segment_after_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "run-session.sqlite3"
    _create_active_run(db_path)
    first_service = RunSessionService(db_path=db_path, id_factory=_id_factory("segment-1"))
    first = first_service.context_for_drop(observed_ts_ms=1_000, setup=_setup("Finder A"))
    _persist_started_segment(db_path, _started_event(first.lifecycle_events))
    restarted_service = RunSessionService(db_path=db_path, id_factory=_id_factory("segment-2"))

    restored = restarted_service.context_for_drop(observed_ts_ms=2_000, setup=_setup("Finder A"))

    assert restored.segment_id == "segment-1"
    assert restored.lifecycle_events == ()


def test_run_session_ends_persisted_active_segment_after_restart_when_setup_changes(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "run-session.sqlite3"
    _create_active_run(db_path)
    first_service = RunSessionService(db_path=db_path, id_factory=_id_factory("segment-1"))
    first = first_service.context_for_drop(observed_ts_ms=1_000, setup=_setup("Finder A"))
    _persist_started_segment(db_path, _started_event(first.lifecycle_events))
    restarted_service = RunSessionService(db_path=db_path, id_factory=_id_factory("segment-2"))

    changed = restarted_service.context_for_drop(observed_ts_ms=2_000, setup=_setup("Finder B"))

    assert changed.segment_id == "segment-2"
    assert len(changed.lifecycle_events) == 2
    ended = changed.lifecycle_events[0]
    started = changed.lifecycle_events[1]
    assert isinstance(ended, RunSegmentEndedEvent)
    assert ended.segment_id == "segment-1"
    assert ended.reason == "setup_changed"
    assert isinstance(started, RunSegmentStartedEvent)
    assert started.segment_id == "segment-2"
    assert started.segment_index == 2


def test_run_session_closes_duplicate_active_segments_after_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "run-session.sqlite3"
    _create_active_run(db_path)
    first_service = RunSessionService(
        db_path=db_path,
        id_factory=_id_factory("segment-1", "segment-2"),
    )
    first = first_service.context_for_drop(observed_ts_ms=1_000, setup=_setup("Finder A"))
    second = first_service.context_for_drop(observed_ts_ms=2_000, setup=_setup("Finder B"))
    _persist_started_segment(db_path, _started_event(first.lifecycle_events))
    _persist_started_segment(db_path, _started_event(second.lifecycle_events))
    restarted_service = RunSessionService(db_path=db_path, id_factory=_id_factory("segment-3"))

    restored = restarted_service.context_for_drop(observed_ts_ms=3_000, setup=_setup("Finder B"))

    assert restored.segment_id == "segment-2"
    assert len(restored.lifecycle_events) == 1
    ended = restored.lifecycle_events[0]
    assert isinstance(ended, RunSegmentEndedEvent)
    assert ended.segment_id == "segment-1"
    assert ended.reason == "stale_active_segment"


def test_run_session_returns_no_context_without_active_run(tmp_path: Path) -> None:
    db_path = tmp_path / "run-session.sqlite3"
    conn = open_sqlite(db_path)
    try:
        ensure_schema(conn)
    finally:
        conn.close()
    service = RunSessionService(db_path=db_path, id_factory=_id_factory("segment-1"))

    context = service.context_for_drop(observed_ts_ms=1_000, setup=_setup("Finder A"))

    assert context.run_id is None
    assert context.segment_id is None
    assert context.lifecycle_events == ()


def _create_active_run(db_path: Path) -> None:
    conn = open_sqlite(db_path)
    try:
        ensure_schema(conn)
        with conn:
            RunState(conn).create_run(name="Test run", activate=True)
    finally:
        conn.close()


def _persist_started_segment(db_path: Path, event: RunSegmentStartedEvent) -> None:
    conn = open_sqlite(db_path)
    try:
        with conn:
            RunSegmentStore(conn).create(
                run_id=event.run_id,
                segment_id=event.segment_id,
                segment_index=event.segment_index,
                started_ts_ms=event.started_ts_ms,
                setup_hash=event.setup_hash,
                setup_snapshot=event.setup_snapshot,
                ts_ms=event.started_ts_ms,
            )
    finally:
        conn.close()


def _started_event(
    lifecycle_events: tuple[RunSegmentEndedEvent | RunSegmentStartedEvent, ...],
) -> RunSegmentStartedEvent:
    started = next(event for event in lifecycle_events if isinstance(event, RunSegmentStartedEvent))
    return started


def _profile(name: str, *, extractor_name: str | None = None) -> MiningEquipmentProfile:
    extractor = (
        MiningToolProfile(name=extractor_name, decay_mpec=Mpec(25))
        if extractor_name is not None
        else None
    )
    return MiningEquipmentProfile(
        finder=MiningToolProfile(name=name, decay_mpec=Mpec(100), radius_m=55.0),
        extractor=extractor,
    )


def _setup(
    name: str,
    *,
    modes_mask: int | None = 1,
    ammo_per_drop: int | None = 1_000,
    probes_per_drop: int | None = None,
    extractor_name: str | None = None,
) -> MiningSegmentSetup:
    return MiningSegmentSetup(
        profile=_profile(name, extractor_name=extractor_name),
        modes_mask=modes_mask,
        ammo_per_drop=ammo_per_drop,
        probes_per_drop=probes_per_drop,
    )


def _id_factory(*ids: str):
    iterator = iter(ids)

    def next_id() -> str:
        return next(iterator)

    return next_id
