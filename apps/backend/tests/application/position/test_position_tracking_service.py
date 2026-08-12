from __future__ import annotations

from zml_backend.application.position.model import (
    PositionSnapshot,
    PositionSource,
    PositionTrackingConfig,
)
from zml_backend.application.position.tracking import PositionTrackingService
from zml_backend.domain.position import WorldPos


def test_position_tracking_service_stores_latest_position() -> None:
    service = PositionTrackingService()

    first = _position(ts_ms=1_000, x=58_000, y=84_000)
    second = _position(ts_ms=2_000, x=58_010, y=84_005)

    service.ingest_snapshot(first)
    service.ingest_snapshot(second)

    assert service.get_latest() == second
    assert service.get_latest_world_pos() == second.position
    assert service.get_history() == (first, second)


def test_position_tracking_service_publishes_updates() -> None:
    published: list[PositionSnapshot] = []
    service = PositionTrackingService(publisher=published.append)
    position = _position(ts_ms=1_000, x=58_000, y=84_000)

    service.ingest_snapshot(position)

    assert published == [position]


def test_position_tracking_service_can_replace_publisher() -> None:
    first_published: list[PositionSnapshot] = []
    second_published: list[PositionSnapshot] = []
    service = PositionTrackingService(publisher=first_published.append)

    first = _position(ts_ms=1_000, x=58_000, y=84_000)
    second = _position(ts_ms=2_000, x=58_010, y=84_005)

    service.ingest_snapshot(first)
    service.set_publisher(second_published.append)
    service.ingest_snapshot(second)

    assert first_published == [first]
    assert second_published == [first, second]
    assert service.get_latest() == second


def test_position_tracking_service_rejects_single_ocr_outlier() -> None:
    published: list[PositionSnapshot] = []
    service = PositionTrackingService(
        publisher=published.append,
        config=PositionTrackingConfig(max_jump_m=20.0, max_speed_mps=20.0),
    )

    stable = _position(ts_ms=1_000, x=58_000, y=84_000)
    outlier = _position(ts_ms=2_000, x=580_000, y=840_000)

    assert service.ingest_snapshot(stable).kind == "accepted"
    decision = service.ingest_snapshot(outlier)

    assert decision.kind == "rejected_outlier"
    assert not decision.accepted
    assert service.get_latest() == stable
    assert published == [stable]


def test_low_confidence_tightens_distance_check_without_automatic_rejection() -> None:
    service = PositionTrackingService(
        config=PositionTrackingConfig(
            max_jump_m=150.0,
            max_speed_mps=120.0,
            low_confidence_threshold=0.4,
            low_confidence_max_distance_m=20.0,
        )
    )
    stable = _position(ts_ms=1_000, x=30_681, y=9_622, confidence=0.92)
    noisy_jump = _position(ts_ms=1_100, x=30_683, y=9_671, confidence=0.14)
    nearby_low_confidence = _position(ts_ms=1_200, x=30_683, y=9_621, confidence=0.20)

    assert service.ingest_snapshot(stable).kind == "accepted"
    rejected = service.ingest_snapshot(noisy_jump)
    accepted = service.ingest_snapshot(nearby_low_confidence)

    assert rejected.kind == "rejected_outlier"
    assert rejected.allowed_m == 20.0
    assert not rejected.accepted
    assert accepted.kind == "accepted"
    assert accepted.allowed_m == 20.0
    assert accepted.accepted
    assert service.get_latest() == nearby_low_confidence


def test_position_tracking_service_accepts_relocation_after_confirmed_cluster() -> None:
    published: list[PositionSnapshot] = []
    service = PositionTrackingService(
        publisher=published.append,
        config=PositionTrackingConfig(
            max_jump_m=20.0,
            max_speed_mps=20.0,
            relocation_confirm_s=5.0,
            relocation_min_samples=3,
            relocation_cluster_radius_m=20.0,
        ),
    )

    stable = _position(ts_ms=1_000, x=58_000, y=84_000)
    relocation_start = _position(ts_ms=2_000, x=60_000, y=86_000)
    relocation_middle = _position(ts_ms=5_000, x=60_004, y=86_002)
    relocation_confirmed = _position(ts_ms=7_000, x=60_008, y=86_004)

    assert service.ingest_snapshot(stable).kind == "accepted"
    assert service.ingest_snapshot(relocation_start).kind == "rejected_outlier"
    assert service.ingest_snapshot(relocation_middle).kind == "suspect_relocation"
    decision = service.ingest_snapshot(relocation_confirmed)

    assert decision.kind == "relocation_accepted"
    assert decision.accepted
    assert service.get_latest() == relocation_confirmed
    assert published == [stable, relocation_confirmed]


def test_position_tracking_service_rejects_stale_reading() -> None:
    service = PositionTrackingService()

    stable = _position(ts_ms=2_000, x=58_000, y=84_000)
    stale = _position(ts_ms=1_000, x=58_001, y=84_001)

    assert service.ingest_snapshot(stable).kind == "accepted"
    decision = service.ingest_snapshot(stale)

    assert decision.kind == "stale_rejected"
    assert service.get_latest() == stable


def test_position_tracking_service_trusts_non_ocr_snapshot() -> None:
    service = PositionTrackingService(
        config=PositionTrackingConfig(max_jump_m=20.0, max_speed_mps=20.0)
    )

    stable = _position(ts_ms=1_000, x=58_000, y=84_000)
    manual_reset = _position(ts_ms=2_000, x=138_260, y=76_275, source="manual")

    assert service.ingest_snapshot(stable).kind == "accepted"
    decision = service.ingest_snapshot(manual_reset)

    assert decision.kind == "trusted_reset"
    assert service.get_latest() == manual_reset


def test_position_tracking_service_keeps_trusted_planet_for_following_ocr_positions() -> None:
    service = PositionTrackingService()
    chat_position = _position(
        ts_ms=1_000,
        x=58_000,
        y=84_000,
        planet="Calypso",
        source="chat",
    )
    ocr_position = _position(ts_ms=2_000, x=58_010, y=84_005)

    service.ingest_snapshot(chat_position)
    decision = service.ingest_snapshot(ocr_position)

    assert decision.kind == "accepted"
    assert decision.snapshot is not None
    assert decision.snapshot.position.planet_name == "Calypso"
    assert service.get_latest() == decision.snapshot
    assert service.get_last_known_planet_name() == "Calypso"
    assert ocr_position.position.planet_name == ""


def test_position_tracking_service_restores_planet_without_restoring_coordinates() -> None:
    service = PositionTrackingService(initial_planet_name="Calypso")

    assert service.get_latest() is None
    assert service.get_latest_world_pos() is None
    assert service.get_last_known_planet_name() == "Calypso"

    decision = service.ingest_snapshot(_position(ts_ms=1_000, x=58_000, y=84_000))

    assert decision.accepted
    assert decision.snapshot is not None
    assert decision.snapshot.position == WorldPos(
        planet_name="Calypso",
        x=58_000,
        y=84_000,
        z=None,
    )


def test_position_tracking_service_prunes_history_by_window_and_limit() -> None:
    service = PositionTrackingService(
        config=PositionTrackingConfig(
            outlier_filter_enabled=False,
            history_window_s=2.0,
            history_max_samples=3,
        )
    )

    for index in range(5):
        service.ingest_snapshot(
            _position(
                ts_ms=1_000 + index * 1_000,
                x=58_000 + index,
                y=84_000,
            )
        )

    history = service.get_history()

    assert [snapshot.observed_ts_ms for snapshot in history] == [3_000, 4_000, 5_000]


def _position(
    *,
    ts_ms: int,
    x: int,
    y: int,
    planet: str = "",
    source: PositionSource = "ocr",
    confidence: float | None = None,
) -> PositionSnapshot:
    return PositionSnapshot(
        observed_ts_ms=ts_ms,
        received_ts_ms=ts_ms + 10,
        position=WorldPos(planet_name=planet, x=x, y=y, z=None),
        source=source,
        confidence=confidence,
    )
