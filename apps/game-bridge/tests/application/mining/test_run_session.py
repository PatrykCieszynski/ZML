from __future__ import annotations

from pathlib import Path

from zml_game_bridge.application.mining.segments.session import RunSessionService
from zml_game_bridge.domain.mining_cost import MiningEquipmentProfile, MiningToolProfile
from zml_game_bridge.domain.mining_events import RunSegmentEndedEvent, RunSegmentStartedEvent
from zml_game_bridge.domain.money import Mpec
from zml_game_bridge.persistence.run_state import RunState
from zml_game_bridge.persistence.schema import ensure_schema
from zml_game_bridge.persistence.sqlite import open_sqlite


def test_run_session_starts_segment_on_first_drop(tmp_path: Path) -> None:
    db_path = tmp_path / "run-session.sqlite3"
    _create_active_run(db_path)
    service = RunSessionService(db_path=db_path, id_factory=_id_factory("segment-1"))

    context = service.context_for_drop(observed_ts_ms=1_000, profile=_profile("Finder A"))

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


def test_run_session_reuses_segment_until_setup_changes(tmp_path: Path) -> None:
    db_path = tmp_path / "run-session.sqlite3"
    _create_active_run(db_path)
    service = RunSessionService(db_path=db_path, id_factory=_id_factory("segment-1", "segment-2"))

    first = service.context_for_drop(observed_ts_ms=1_000, profile=_profile("Finder A"))
    second = service.context_for_drop(observed_ts_ms=2_000, profile=_profile("Finder A"))
    third = service.context_for_drop(observed_ts_ms=3_000, profile=_profile("Finder B"))

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


def test_run_session_returns_no_context_without_active_run(tmp_path: Path) -> None:
    db_path = tmp_path / "run-session.sqlite3"
    conn = open_sqlite(db_path)
    try:
        ensure_schema(conn)
    finally:
        conn.close()
    service = RunSessionService(db_path=db_path, id_factory=_id_factory("segment-1"))

    context = service.context_for_drop(observed_ts_ms=1_000, profile=_profile("Finder A"))

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


def _profile(name: str) -> MiningEquipmentProfile:
    return MiningEquipmentProfile(
        finder=MiningToolProfile(name=name, decay_mpec=Mpec(100), radius_m=55.0),
    )


def _id_factory(*ids: str):
    iterator = iter(ids)

    def next_id() -> str:
        return next(iterator)

    return next_id
