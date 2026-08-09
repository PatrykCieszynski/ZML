from __future__ import annotations

import copy
import json

import pytest
from test_message_round_trips import AGENT_MESSAGES, BRIDGE_MESSAGES

from zml_ocr_protocol import (
    MAX_LINE_BYTES,
    MalformedMessageError,
    MessageTooLargeError,
    MessageValidationError,
    UnsupportedProtocolVersionError,
    decode_agent_message,
    decode_bridge_message,
)


def _json(payload: object) -> str:
    return json.dumps(payload, allow_nan=True)


@pytest.mark.parametrize("line", ["", "\n", "not-json", "[]", "{}\n{}\n"])
def test_malformed_lines_are_rejected(line: str) -> None:
    with pytest.raises(MalformedMessageError):
        decode_agent_message(line)


def test_invalid_utf8_is_rejected() -> None:
    with pytest.raises(MalformedMessageError):
        decode_agent_message(b"\xff\n")


def test_oversized_line_is_rejected_before_json_parsing() -> None:
    line = b"{" + (b" " * MAX_LINE_BYTES) + b"}\n"
    with pytest.raises(MessageTooLargeError) as exc_info:
        decode_agent_message(line)
    assert exc_info.value.actual_bytes == len(line)
    assert exc_info.value.max_bytes == MAX_LINE_BYTES


def test_unsupported_protocol_version_has_a_specific_error() -> None:
    payload = copy.deepcopy(AGENT_MESSAGES[0])
    payload["protocol_version"] = 2
    with pytest.raises(UnsupportedProtocolVersionError) as exc_info:
        decode_agent_message(_json(payload))
    assert exc_info.value.received_version == 2
    assert exc_info.value.supported_versions == (1,)


@pytest.mark.parametrize("version", ["1", True, None])
def test_malformed_protocol_version_is_a_validation_error(version: object) -> None:
    payload = copy.deepcopy(AGENT_MESSAGES[0])
    payload["protocol_version"] = version
    with pytest.raises(MessageValidationError):
        decode_agent_message(_json(payload))


def test_missing_protocol_version_is_rejected() -> None:
    payload = copy.deepcopy(AGENT_MESSAGES[0])
    del payload["protocol_version"]
    with pytest.raises(MessageValidationError):
        decode_agent_message(_json(payload))


def test_extra_top_level_field_is_rejected() -> None:
    payload = copy.deepcopy(AGENT_MESSAGES[0])
    payload["unexpected"] = True
    with pytest.raises(MessageValidationError):
        decode_agent_message(_json(payload))


def test_unknown_message_type_is_rejected() -> None:
    payload = copy.deepcopy(AGENT_MESSAGES[0])
    payload["type"] = "mystery"
    with pytest.raises(MessageValidationError):
        decode_agent_message(_json(payload))


def test_unknown_finder_kind_is_rejected() -> None:
    payload = copy.deepcopy(AGENT_MESSAGES[2])
    assert isinstance(payload["payload"], dict)
    payload["payload"]["kind"] = "mystery"
    with pytest.raises(MessageValidationError):
        decode_agent_message(_json(payload))


def test_missing_required_hit_field_is_rejected() -> None:
    payload = copy.deepcopy(AGENT_MESSAGES[6])
    assert isinstance(payload["payload"], dict)
    del payload["payload"]["resource_name"]
    with pytest.raises(MessageValidationError):
        decode_agent_message(_json(payload))


def test_string_is_not_coerced_to_integer() -> None:
    payload = copy.deepcopy(AGENT_MESSAGES[1])
    assert isinstance(payload["payload"], dict)
    position = payload["payload"]["position"]
    assert isinstance(position, dict)
    position["x"] = "65432"
    with pytest.raises(MessageValidationError):
        decode_agent_message(_json(payload))


def test_non_finite_number_is_rejected() -> None:
    payload = copy.deepcopy(AGENT_MESSAGES[6])
    assert isinstance(payload["payload"], dict)
    payload["payload"]["range_m"] = float("nan")
    with pytest.raises(MalformedMessageError):
        decode_agent_message(_json(payload))


def test_invalid_roi_geometry_is_rejected() -> None:
    payload = copy.deepcopy(BRIDGE_MESSAGES[0])
    command_payload = payload["payload"]
    assert isinstance(command_payload, dict)
    config = command_payload["config"]
    assert isinstance(config, dict)
    profile = config["roi_profile"]
    assert isinstance(profile, dict)
    position_rois = profile["position_rois"]
    assert isinstance(position_rois, dict)
    lon = position_rois["lon"]
    assert isinstance(lon, dict)
    lon["x2"] = lon["x1"]
    with pytest.raises(MessageValidationError):
        decode_bridge_message(_json(payload))


def test_inconsistent_command_result_is_rejected() -> None:
    payload = copy.deepcopy(AGENT_MESSAGES[10])
    command_payload = payload["payload"]
    assert isinstance(command_payload, dict)
    command_payload["applied_revision"] = None
    with pytest.raises(MessageValidationError):
        decode_agent_message(_json(payload))


def test_message_direction_is_enforced() -> None:
    with pytest.raises(MessageValidationError):
        decode_agent_message(_json(BRIDGE_MESSAGES[1]))
    with pytest.raises(MessageValidationError):
        decode_bridge_message(_json(AGENT_MESSAGES[0]))
