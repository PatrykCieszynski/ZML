from __future__ import annotations

import threading
from io import BytesIO
from pathlib import Path

import pytest
from zml_ocr_protocol import (
    CommandResultMessage,
    HeartbeatMessage,
    HelloMessage,
    ShutdownCommand,
    ShutdownPayload,
    decode_agent_message,
    encode_message,
)
from zml_ocr_protocol.messages import (
    ApplyConfigCommand,
    ApplyConfigPayload,
    FinderPanelPayload,
    FinderRecordingConfigPayload,
    FinderRuntimeConfig,
    OcrConfigSnapshot,
    OcrRoiProfilePayload,
    PixelRectPayload,
    PositionRoisPayload,
    PositionRuntimeConfig,
    PositionSnapshotRecordingConfigPayload,
    ProfilingConfig,
    RelativeRectPayload,
    ScreenRoiAnchor,
    ScreenRoiPayload,
    ScreenRoisPayload,
)

from zml_ocr_agent.config import OcrRoiProfile
from zml_ocr_agent.message_factory import AgentMessageFactory
from zml_ocr_agent.stdio import AgentRuntimeState, ProtocolWriter, run_stdio


def test_protocol_writer_assigns_wire_sequence_in_emission_order() -> None:
    output = BytesIO()
    runtime_state = AgentRuntimeState()
    writer = ProtocolWriter(output, runtime_state=runtime_state)
    factory = AgentMessageFactory(
        clock_ms=lambda: 100,
        message_id_factory=lambda: "a" * 32,
    )
    hello = factory.hello()
    status = factory.status(
        state="waiting_for_window",
        capture_available=False,
        code="window_unavailable",
        detail="window missing",
    )
    heartbeat = factory.heartbeat(state="degraded", capture_available=False)

    writer.write(hello)
    writer.write(heartbeat)
    writer.write(status)

    messages = [decode_agent_message(line) for line in output.getvalue().splitlines()]
    assert len(messages) == 3
    assert isinstance(messages[0], HelloMessage)
    assert isinstance(messages[1], HeartbeatMessage)
    assert [message.sequence_id for message in messages] == [0, 1, 2]


def test_runtime_state_tracks_latest_status_for_heartbeat() -> None:
    runtime_state = AgentRuntimeState()
    factory = AgentMessageFactory(
        clock_ms=lambda: 100,
        message_id_factory=lambda: "a" * 32,
    )

    runtime_state.observe(
        factory.status(
            state="waiting_for_window",
            capture_available=False,
            code="window_unavailable",
            detail="window missing",
        )
    )

    assert runtime_state.snapshot() == ("waiting_for_window", False)


def test_stdio_applies_config_idempotently_rejects_stale_revision_and_shuts_down(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner_calls: list[dict[str, object]] = []

    def fake_runner(**kwargs: object) -> None:
        runner_calls.append(kwargs)
        stop_event = kwargs["stop_event"]
        assert isinstance(stop_event, threading.Event)
        stop_event.wait(timeout=1.0)

    monkeypatch.setattr(
        "zml_ocr_agent.stdio.preload_tesserocr_preserving_sigint_handler",
        lambda: None,
    )
    monkeypatch.setattr("zml_ocr_agent.stdio.start_ocr_input", fake_runner)
    apply = _apply_config(tmp_path=tmp_path, revision=4, command_id="a" * 32)
    duplicate = apply.model_copy(update={"command_id": "b" * 32})
    stale = apply.model_copy(
        update={
            "command_id": "c" * 32,
            "payload": apply.payload.model_copy(update={"revision": 3}),
        }
    )
    shutdown = ShutdownCommand(
        protocol_version=1,
        type="shutdown",
        command_id="d" * 32,
        sent_ts_ms=2,
        payload=ShutdownPayload(reason="backend_shutdown"),
    )
    stdout = BytesIO()

    exit_code = run_stdio(
        stdin=BytesIO(
            encode_message(apply)
            + encode_message(duplicate)
            + encode_message(stale)
            + encode_message(shutdown)
        ),
        stdout=stdout,
    )

    assert exit_code == 0
    assert len(runner_calls) == 1
    assert runner_calls[0]["target_hz"] == 7.5
    assert runner_calls[0]["finder_debug_logging"] is True
    roi_profile = runner_calls[0]["roi_profile"]
    assert isinstance(roi_profile, OcrRoiProfile)
    assert roi_profile.name == "test-profile"
    results = [
        message
        for line in stdout.getvalue().splitlines()
        if isinstance((message := decode_agent_message(line)), CommandResultMessage)
    ]
    assert [(result.payload.command_type, result.payload.status) for result in results] == [
        ("apply_config", "ok"),
        ("apply_config", "ok"),
        ("apply_config", "error"),
        ("shutdown", "ok"),
    ]
    assert results[0].payload.applied_revision == 4
    assert results[1].payload.applied_revision == 4
    assert results[2].payload.error is not None
    assert results[2].payload.error.code == "stale_config_revision"


def _apply_config(*, tmp_path: Path, revision: int, command_id: str) -> ApplyConfigCommand:
    def screen_roi(
        name: str,
        *,
        anchor: ScreenRoiAnchor = "top_left",
    ) -> ScreenRoiPayload:
        return ScreenRoiPayload(
            name=name,
            anchor=anchor,
            x=3,
            y=3,
            width=347,
            height=239,
            enabled=True,
        )

    profile = OcrRoiProfilePayload(
        schema_version=1,
        name="test-profile",
        screen_rois=ScreenRoisPayload(
            compass=screen_roi("compass"),
            finder=screen_roi("finder", anchor="bottom_left"),
            deeds=screen_roi("deeds"),
            loot=None,
        ),
        position_rois=PositionRoisPayload(
            planet=PixelRectPayload(x1=1, x2=2, y1=1, y2=2),
            lon=PixelRectPayload(x1=2, x2=3, y1=2, y2=3),
            lat=PixelRectPayload(x1=3, x2=4, y1=3, y2=4),
        ),
        finder_panel=FinderPanelPayload(
            radar=RelativeRectPayload(x1=0.0, y1=0.0, x2=0.4, y2=0.4),
            modes=RelativeRectPayload(x1=0.0, y1=0.5, x2=0.4, y2=1.0),
            details=RelativeRectPayload(x1=0.5, y1=0.0, x2=1.0, y2=0.3),
            units=RelativeRectPayload(x1=0.5, y1=0.7, x2=1.0, y2=1.0),
            status=RelativeRectPayload(x1=0.5, y1=0.3, x2=1.0, y2=0.7),
        ),
    )
    config = OcrConfigSnapshot(
        capture_hz=7.5,
        capture_artifacts_dir=str(tmp_path / "captures"),
        roi_profile=profile,
        finder=FinderRuntimeConfig(
            presence_check_enabled=True,
            debug_logging=True,
            recording=FinderRecordingConfigPayload(
                modes=["manual"],
                directory=str(tmp_path / "finder"),
                interval_ms=2_000,
                max_samples=3,
            ),
        ),
        position=PositionRuntimeConfig(
            snapshot_recording=PositionSnapshotRecordingConfigPayload(
                enabled=True,
                directory=str(tmp_path / "position"),
                interval_ms=3_000,
                max_samples=4,
            )
        ),
        profiling=ProfilingConfig(enabled=True, interval_ms=5_000),
    )
    return ApplyConfigCommand(
        protocol_version=1,
        type="apply_config",
        command_id=command_id,
        sent_ts_ms=1,
        payload=ApplyConfigPayload(revision=revision, config=config),
    )
