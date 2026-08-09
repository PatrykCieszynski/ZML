from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from zml_backend.domain.mining_events import (
    MiningClaimCreatedEvent,
    MiningClaimDepletedEvent,
    MiningClaimExpiredEvent,
    MiningClaimIgnoredEvent,
    MiningClaimUpdatedEvent,
)
from zml_backend.domain.position import WorldPos
from zml_backend.persistence.event_writer import EventWriter
from zml_backend.persistence.mining_claims import MiningClaimProjector, MiningClaimReader
from zml_backend.persistence.runs import RunSegmentStore, RunStore
from zml_backend.persistence.schema import ensure_schema
from zml_backend.persistence.sqlite import open_sqlite


def _open_test_db(tmp_path: Path) -> sqlite3.Connection:
    conn = open_sqlite(tmp_path / "mining-claims.sqlite3")
    ensure_schema(conn)
    _create_test_run_segment(conn)
    return conn


def test_mining_claim_projector_stores_claim_read_model(tmp_path: Path) -> None:
    conn = _open_test_db(tmp_path)
    try:
        env = EventWriter(conn, projector=MiningClaimProjector()).write(_claim_created_event())

        row = MiningClaimReader(conn).get("claim-1")
        assert row is not None
        assert row.claim_id == "claim-1"
        assert row.created_event_id == env.event_id
        assert row.hit_id == "hit-1"
        assert row.drop_id == "drop-1"
        assert row.run_id == 1
        assert row.segment_id == "segment-1"
        assert row.observed_ts_ms == 2_000
        assert row.position == WorldPos(planet_name="Calypso", x=58_890, y=84_639, z=None)
        assert row.search_radius_m == 55.0
        assert row.resource_name == "Lysterium Stone"
        assert row.mining_type == "ore"
        assert row.size_label == "Minimal"
        assert row.size_index == 1
        assert row.expected_expires_ts_ms == 3_602_000
        assert row.range_m == 51.14
        assert row.depth_m == 53.0
        assert row.status == "active"
        assert row.depleted_event_id is None
    finally:
        conn.close()


def test_mining_claim_projector_marks_claim_depleted(tmp_path: Path) -> None:
    conn = _open_test_db(tmp_path)
    try:
        writer = EventWriter(conn, projector=MiningClaimProjector())
        writer.write(_claim_created_event())
        event_dt = datetime(2026, 1, 10, 12, 37, 50)
        depleted_env = writer.write(
            MiningClaimDepletedEvent(
                claim_id="claim-1",
                drop_id="drop-1",
                hit_id="hit-1",
                event_dt=event_dt,
                position=WorldPos(planet_name="Calypso", x=58_894, y=84_642, z=None),
                distance_m=5.0,
                raw="depleted raw",
            )
        )

        row = MiningClaimReader(conn).get("claim-1")
        assert row is not None
        assert row.status == "depleted"
        assert row.depleted_event_id == depleted_env.event_id
        assert row.depleted_event_dt == event_dt
        assert row.depleted_position == WorldPos(
            planet_name="Calypso",
            x=58_894,
            y=84_642,
            z=None,
        )
        assert row.depleted_distance_m == 5.0
        assert MiningClaimReader(conn).list_active(now_ts_ms=2_500) == []
    finally:
        conn.close()


def test_mining_claim_projector_updates_claim_from_later_hint(tmp_path: Path) -> None:
    conn = _open_test_db(tmp_path)
    try:
        writer = EventWriter(conn, projector=MiningClaimProjector())
        writer.write(
            MiningClaimCreatedEvent(
                claim_id="claim-1",
                hit_id=None,
                drop_id="drop-1",
                run_id=1,
                segment_id="segment-1",
                observed_ts_ms=1_000,
                position=WorldPos(planet_name="Calypso", x=58_890, y=84_639, z=None),
                search_radius_m=55.0,
                resource_name="Narcanisum Stone",
                mining_type="ore",
                size_label=None,
                size_index=None,
                expected_expires_ts_ms=None,
            )
        )

        writer.write(
            MiningClaimUpdatedEvent(
                claim_id="claim-1",
                updated_ts_ms=2_000,
                hit_id="hit-1",
                drop_id="drop-1",
                resource_name="Narcanisum Stone",
                mining_type="ore",
                size_label="Tiny",
                size_index=2,
                expected_expires_ts_ms=3_602_000,
                range_m=51.14,
                depth_m=53.0,
            )
        )

        row = MiningClaimReader(conn).get("claim-1")
        assert row is not None
        assert row.hit_id == "hit-1"
        assert row.resource_name == "Narcanisum Stone"
        assert row.mining_type == "ore"
        assert row.size_label == "Tiny"
        assert row.size_index == 2
        assert row.expected_expires_ts_ms == 3_602_000
        assert row.range_m == 51.14
        assert row.depth_m == 53.0
    finally:
        conn.close()


def test_mining_claim_reader_lists_active_unexpired_claims(tmp_path: Path) -> None:
    conn = _open_test_db(tmp_path)
    try:
        writer = EventWriter(conn, projector=MiningClaimProjector())
        writer.write(_claim_created_event(claim_id="expired", expected_expires_ts_ms=1_000))
        writer.write(_claim_created_event(claim_id="active", expected_expires_ts_ms=2_000))
        writer.write(_claim_created_event(claim_id="non-expiring", expected_expires_ts_ms=None))

        claims = MiningClaimReader(conn).list_active(now_ts_ms=1_500)

        assert [claim.claim_id for claim in claims] == ["active", "non-expiring"]
    finally:
        conn.close()


def test_mining_claim_projector_marks_claim_ignored(tmp_path: Path) -> None:
    conn = _open_test_db(tmp_path)
    try:
        writer = EventWriter(conn, projector=MiningClaimProjector())
        writer.write(_claim_created_event())
        ignored_env = writer.write(
            MiningClaimIgnoredEvent(
                claim_id="claim-1",
                ignored_ts_ms=2_500,
                reason="manual map action",
                drop_id="drop-1",
                hit_id="hit-1",
                run_id=1,
                segment_id="segment-1",
            )
        )

        row = MiningClaimReader(conn).get("claim-1")
        assert row is not None
        assert row.status == "ignored"
        assert row.ignored_event_id == ignored_env.event_id
        assert row.ignored_ts_ms == 2_500
        assert row.ignored_reason == "manual map action"
        assert MiningClaimReader(conn).list_active(now_ts_ms=3_000) == []
    finally:
        conn.close()


def test_mining_claim_projector_marks_claim_expired(tmp_path: Path) -> None:
    conn = _open_test_db(tmp_path)
    try:
        writer = EventWriter(conn, projector=MiningClaimProjector())
        writer.write(_claim_created_event(expected_expires_ts_ms=2_000))
        expired_env = writer.write(
            MiningClaimExpiredEvent(
                claim_id="claim-1",
                expired_ts_ms=3_000,
                expected_expires_ts_ms=2_000,
                drop_id="drop-1",
                hit_id="hit-1",
                run_id=1,
                segment_id="segment-1",
            )
        )

        row = MiningClaimReader(conn).get("claim-1")
        assert row is not None
        assert row.status == "expired"
        assert row.expired_event_id == expired_env.event_id
        assert row.expired_ts_ms == 3_000
        assert MiningClaimReader(conn).list_active() == []
        assert MiningClaimReader(conn).list_active(now_ts_ms=3_000) == []
    finally:
        conn.close()


def _claim_created_event(
    *,
    claim_id: str = "claim-1",
    expected_expires_ts_ms: int | None = 3_602_000,
) -> MiningClaimCreatedEvent:
    return MiningClaimCreatedEvent(
        claim_id=claim_id,
        hit_id="hit-1",
        drop_id="drop-1",
        run_id=1,
        segment_id="segment-1",
        observed_ts_ms=2_000,
        position=WorldPos(planet_name="Calypso", x=58_890, y=84_639, z=None),
        search_radius_m=55.0,
        resource_name="Lysterium Stone",
        mining_type="ore",
        size_label="Minimal",
        size_index=1,
        expected_expires_ts_ms=expected_expires_ts_ms,
        range_m=51.14,
        depth_m=53.0,
    )


def _create_test_run_segment(conn: sqlite3.Connection) -> None:
    with conn:
        run_id = RunStore(conn).create_run(
            name="Test run",
            notes=None,
            ts_ms=1_000,
            status="running",
        )
        RunSegmentStore(conn).create(
            run_id=run_id,
            segment_id="segment-1",
            segment_index=1,
            started_ts_ms=1_000,
            setup_hash="setup-hash",
            setup_snapshot={"finder": {"name": "Finder"}},
            ts_ms=1_000,
        )
