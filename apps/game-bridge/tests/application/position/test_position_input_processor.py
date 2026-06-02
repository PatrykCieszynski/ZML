from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from zml_game_bridge.application.position.input_processor import PositionInputProcessor
from zml_game_bridge.application.position.model import PositionSnapshot, PositionTrackingConfig
from zml_game_bridge.application.position.tracking import PositionTrackingService
from zml_game_bridge.domain.position import WorldPos
from zml_game_bridge.events.base import SignalBase
from zml_game_bridge.inputs.chat.model import ChannelType
from zml_game_bridge.inputs.chat.signals import PlayerPosWaypointSignal


@dataclass(frozen=True, slots=True)
class OtherSignal(SignalBase):
    pass


def test_position_input_processor_ingests_player_pos_waypoint_as_trusted_chat_position() -> None:
    published: list[PositionSnapshot] = []
    service = PositionTrackingService(
        publisher=published.append,
        config=PositionTrackingConfig(max_jump_m=20.0, max_speed_mps=20.0),
    )
    processor = PositionInputProcessor(service, clock_ms=lambda: 10_000)

    stable = PositionSnapshot(
        observed_ts_ms=1_000,
        received_ts_ms=1_010,
        position=WorldPos(planet_name="", x=58_000, y=84_000, z=None),
        source="ocr",
    )
    service.ingest_snapshot(stable)

    position = WorldPos(planet_name="ROCKTROPIA", x=132_623, y=88_329, z=11)
    signal = PlayerPosWaypointSignal(
        event_dt=datetime(2026, 5, 25, 12, 0, 0),
        channel_type=ChannelType.SYSTEM,
        channel_token="System",
        raw="2026-05-25 12:00:00 [System] [] [ROCKTROPIA, 132623, 88329, 11, Waypoint]",
        position=position,
    )

    events = processor.process_signal(signal)

    latest = service.get_latest()
    assert events == ()
    assert latest is not None
    assert latest.position == position
    assert latest.source == "chat"
    assert latest.confidence == 1.0
    assert latest.observed_ts_ms == 10_000
    assert latest.received_ts_ms == 10_000
    assert published == [stable, latest]


def test_position_input_processor_ignores_non_position_signal() -> None:
    service = PositionTrackingService()
    processor = PositionInputProcessor(service, clock_ms=lambda: 10_000)

    events = processor.process_signal(OtherSignal())

    assert events == ()
    assert service.get_latest() is None
