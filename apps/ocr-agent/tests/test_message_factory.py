from __future__ import annotations

import pytest
from zml_ocr_protocol import (
    FinderSignalMessage,
    HeartbeatMessage,
    HelloMessage,
    PositionMessage,
    StatusMessage,
)

from zml_ocr_agent.pipelines.mining_finder.model import MiningFinderSignal
from zml_ocr_agent.pipelines.model import WorldPosition
from zml_ocr_agent.pipelines.position.model import OcrPosition
from zml_ocr_agent.runtime.message_factory import AgentMessageFactory


def test_factory_emits_ordered_hello_position_status_and_heartbeat_messages() -> None:
    timestamps = iter([100, 101, 102, 103, 104])
    message_ids = iter(["a" * 32, "b" * 32, "c" * 32, "d" * 32])
    factory = AgentMessageFactory(
        clock_ms=lambda: next(timestamps),
        message_id_factory=lambda: next(message_ids),
        agent_version="9.8.7",
        pid=123,
    )

    hello = factory.hello()
    position = factory.position(
        OcrPosition(
            ts_ms=1_000,
            position=WorldPosition(planet_name="Calypso", x=58_000, y=84_000, z=None),
        ),
        roi_name="compass",
    )
    status = factory.status(
        state="waiting_for_window",
        capture_available=False,
        code="window_unavailable",
        detail="window missing",
    )
    heartbeat = factory.heartbeat(
        state="waiting_for_window",
        capture_available=False,
    )

    assert isinstance(hello, HelloMessage)
    assert hello.sequence_id == 0
    assert hello.payload.agent_version == "9.8.7"
    assert hello.payload.pid == 123
    assert "heartbeat" in hello.payload.capabilities
    assert isinstance(position, PositionMessage)
    assert position.sequence_id == 1
    assert position.observed_ts_ms == 1_000
    assert position.payload.position.x == 58_000
    assert isinstance(status, StatusMessage)
    assert status.sequence_id == 2
    assert status.payload.state == "waiting_for_window"
    assert isinstance(heartbeat, HeartbeatMessage)
    assert heartbeat.sequence_id == 3
    assert heartbeat.payload.state == "waiting_for_window"


@pytest.mark.parametrize(
    ("signal", "expected_kind"),
    [
        (MiningFinderSignal(ts_ms=1, kind="probe_fired"), "probe_fired"),
        (
            MiningFinderSignal(ts_ms=2, kind="finder_modes_changed", modes_mask=3),
            "finder_modes_changed",
        ),
        (
            MiningFinderSignal(ts_ms=3, kind="finder_mode_invalidated"),
            "finder_mode_invalidated",
        ),
        (
            MiningFinderSignal(ts_ms=4, kind="finder_units_changed", probes_per_drop=2),
            "finder_units_changed",
        ),
        (
            MiningFinderSignal(
                ts_ms=5,
                kind="finder_hit_hint",
                hit_size_label="Small",
                hit_size_index=3,
                resource_name="Lysterium Stone",
            ),
            "finder_hit_hint",
        ),
        (
            MiningFinderSignal(ts_ms=6, kind="finder_no_resources"),
            "finder_no_resources",
        ),
    ],
)
def test_factory_maps_every_finder_observation(
    signal: MiningFinderSignal,
    expected_kind: str,
) -> None:
    factory = AgentMessageFactory(
        clock_ms=lambda: 100,
        message_id_factory=lambda: "a" * 32,
    )

    message = factory.finder(signal, roi_name="finder")

    assert isinstance(message, FinderSignalMessage)
    assert message.observed_ts_ms == signal.ts_ms
    assert message.payload.kind == expected_kind
    assert message.payload.roi_name == "finder"
