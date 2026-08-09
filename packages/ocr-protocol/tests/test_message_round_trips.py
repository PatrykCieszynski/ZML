from __future__ import annotations

import json
from collections.abc import Mapping

import pytest

from zml_ocr_protocol import decode_agent_message, decode_bridge_message, encode_message

MESSAGE_ID = "11111111111111111111111111111111"
COMMAND_ID = "22222222222222222222222222222222"
CAPTURE_ID = "33333333333333333333333333333333"


def _agent_message(
    message_type: str,
    payload: Mapping[str, object],
    *,
    sequence_id: int,
    observed_ts_ms: int | None = None,
) -> dict[str, object]:
    message: dict[str, object] = {
        "protocol_version": 1,
        "type": message_type,
        "message_id": MESSAGE_ID,
        "sequence_id": sequence_id,
        "emitted_ts_ms": 1_780_000_000_012,
        "payload": dict(payload),
    }
    if observed_ts_ms is not None:
        message["observed_ts_ms"] = observed_ts_ms
    return message


def _finder_message(payload: Mapping[str, object], *, sequence_id: int) -> dict[str, object]:
    return _agent_message(
        "finder_signal",
        payload,
        sequence_id=sequence_id,
        observed_ts_ms=1_780_000_000_000,
    )


def valid_config() -> dict[str, object]:
    def screen_roi(
        name: str,
        *,
        anchor: str = "top_left",
        enabled: bool = True,
    ) -> dict[str, object]:
        return {
            "name": name,
            "anchor": anchor,
            "x": 3,
            "y": 3,
            "width": 347,
            "height": 239,
            "enabled": enabled,
        }

    return {
        "capture_hz": 10.0,
        "capture_artifacts_dir": "C:/zml/tmp/ocr-captures",
        "roi_profile": {
            "schema_version": 1,
            "name": "mvp-default",
            "screen_rois": {
                "compass": screen_roi("compass_mvp_absolute"),
                "finder": screen_roi(
                    "finder_mvp_bottom_left",
                    anchor="bottom_left",
                ),
                "deeds": screen_roi("deeds_mvp_left_panel"),
                "loot": None,
            },
            "position_rois": {
                "planet": {"x1": 23, "x2": 362, "y1": 0, "y2": 30},
                "lon": {"x1": 85, "x2": 145, "y1": 350, "y2": 370},
                "lat": {"x1": 90, "x2": 145, "y1": 375, "y2": 395},
            },
            "finder_panel": {
                "radar": {"x1": 0.02, "y1": 0.03, "x2": 0.48, "y2": 0.70},
                "modes": {"x1": 0.02, "y1": 0.72, "x2": 0.48, "y2": 0.98},
                "details": {"x1": 0.50, "y1": 0.03, "x2": 0.98, "y2": 0.35},
                "units": {"x1": 0.50, "y1": 0.72, "x2": 0.98, "y2": 0.98},
                "status": {"x1": 0.50, "y1": 0.36, "x2": 0.98, "y2": 0.70},
            },
        },
        "finder": {
            "presence_check_enabled": True,
            "debug_logging": False,
            "recording": {
                "modes": ["manual", "interval"],
                "directory": "C:/zml/ocr/finder-crops",
                "interval_ms": 60_000,
                "max_samples": 1,
            },
        },
        "position": {
            "snapshot_recording": {
                "enabled": False,
                "directory": "C:/zml/ocr/position-roi",
                "interval_ms": 60_000,
                "max_samples": 1,
            }
        },
        "profiling": {"enabled": False, "interval_ms": 10_000},
    }


AGENT_MESSAGES: list[dict[str, object]] = [
    _agent_message(
        "hello",
        {
            "agent_version": "0.1.0",
            "pid": 1234,
            "started_ts_ms": 1_780_000_000_000,
            "capabilities": [
                "position",
                "finder",
                "status",
                "heartbeat",
                "apply_config",
                "capture_frame",
                "shutdown",
            ],
        },
        sequence_id=0,
    ),
    _agent_message(
        "position",
        {
            "position": {"planet_name": "Calypso", "x": 65_432, "y": 77_777, "z": None},
            "confidence": None,
            "roi_name": "compass_mvp_absolute",
        },
        sequence_id=1,
        observed_ts_ms=1_780_000_000_000,
    ),
    _finder_message(
        {
            "kind": "probe_fired",
            "modes_mask": 1,
            "probes_per_drop": 2,
            "ammo_per_drop": None,
            "raw_status_text": "Deploying probe",
            "roi_name": "finder_mvp_bottom_left",
            "debug": {"status_score": 0.95},
        },
        sequence_id=2,
    ),
    _finder_message(
        {
            "kind": "finder_modes_changed",
            "modes_mask": 3,
            "previous_modes_mask": 1,
            "roi_name": "finder_mvp_bottom_left",
            "debug": {},
        },
        sequence_id=3,
    ),
    _finder_message(
        {
            "kind": "finder_mode_invalidated",
            "previous_modes_mask": 3,
            "roi_name": "finder_mvp_bottom_left",
            "debug": {},
        },
        sequence_id=4,
    ),
    _finder_message(
        {
            "kind": "finder_units_changed",
            "probes_per_drop": 2,
            "ammo_per_drop": 1_000,
            "raw_units_text": "2 probes / 1.00 PED",
            "roi_name": "finder_mvp_bottom_left",
            "debug": {},
        },
        sequence_id=5,
    ),
    _finder_message(
        {
            "kind": "finder_hit_hint",
            "size_label": "Minimal",
            "size_index": 1,
            "resource_name": "Lysterium Stone",
            "range_m": 8.8,
            "depth_m": 125.0,
            "raw_status_text": "Resource found: Minimal",
            "raw_details_text": "Lysterium Stone 8.8m 125m",
            "roi_name": "finder_mvp_bottom_left",
            "debug": {},
        },
        sequence_id=6,
    ),
    _finder_message(
        {
            "kind": "finder_no_resources",
            "raw_status_text": "No resources found",
            "roi_name": "finder_mvp_bottom_left",
            "debug": {},
        },
        sequence_id=7,
    ),
    _agent_message(
        "status",
        {
            "state": "waiting_for_window",
            "capture_available": False,
            "applied_revision": 4,
            "code": "window_unavailable",
            "detail": "Entropia Universe window is unavailable",
        },
        sequence_id=8,
    ),
    _agent_message(
        "heartbeat",
        {
            "state": "running",
            "capture_available": True,
            "applied_revision": 4,
        },
        sequence_id=9,
    ),
    _agent_message(
        "command_result",
        {
            "command_id": COMMAND_ID,
            "command_type": "apply_config",
            "status": "ok",
            "applied_revision": 4,
            "capture": None,
            "error": None,
        },
        sequence_id=10,
    ),
    _agent_message(
        "command_result",
        {
            "command_id": COMMAND_ID,
            "command_type": "capture_frame",
            "status": "ok",
            "applied_revision": 4,
            "capture": {
                "capture_id": CAPTURE_ID,
                "path_token": "capture-0001.png",
                "format": "png",
                "region": "window",
                "captured_ts_ms": 1_780_000_000_000,
                "width_px": 2560,
                "height_px": 1440,
                "roi_name": None,
            },
            "error": None,
        },
        sequence_id=11,
    ),
    _agent_message(
        "command_result",
        {
            "command_id": COMMAND_ID,
            "command_type": "capture_frame",
            "status": "error",
            "applied_revision": 4,
            "capture": None,
            "error": {
                "code": "window_unavailable",
                "message": "Cannot capture the target window",
                "retryable": True,
            },
        },
        sequence_id=12,
    ),
]

BRIDGE_MESSAGES: list[dict[str, object]] = [
    {
        "protocol_version": 1,
        "type": "apply_config",
        "command_id": COMMAND_ID,
        "sent_ts_ms": 1_780_000_000_000,
        "payload": {"revision": 4, "config": valid_config()},
    },
    {
        "protocol_version": 1,
        "type": "capture_frame",
        "command_id": COMMAND_ID,
        "sent_ts_ms": 1_780_000_000_000,
        "payload": {"purpose": "calibration", "region": "window"},
    },
    {
        "protocol_version": 1,
        "type": "shutdown",
        "command_id": COMMAND_ID,
        "sent_ts_ms": 1_780_000_000_000,
        "payload": {"reason": "backend_shutdown"},
    },
]


@pytest.mark.parametrize("payload", AGENT_MESSAGES, ids=lambda item: str(item["type"]))
def test_agent_message_round_trip(payload: dict[str, object]) -> None:
    decoded = decode_agent_message(json.dumps(payload))
    assert decode_agent_message(encode_message(decoded)) == decoded


@pytest.mark.parametrize("payload", BRIDGE_MESSAGES, ids=lambda item: str(item["type"]))
def test_bridge_message_round_trip(payload: dict[str, object]) -> None:
    decoded = decode_bridge_message(json.dumps(payload))
    assert decode_bridge_message(encode_message(decoded)) == decoded
