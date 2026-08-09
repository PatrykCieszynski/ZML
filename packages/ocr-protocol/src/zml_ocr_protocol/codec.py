from __future__ import annotations

import json

from pydantic import TypeAdapter, ValidationError

from zml_ocr_protocol.errors import (
    MalformedMessageError,
    MessageTooLargeError,
    MessageValidationError,
    UnsupportedProtocolVersionError,
)
from zml_ocr_protocol.messages import (
    SUPPORTED_PROTOCOL_VERSIONS,
    AgentToBridgeMessage,
    BridgeToAgentMessage,
    WireMessage,
)

MAX_LINE_BYTES = 64 * 1024

_AGENT_MESSAGE_ADAPTER = TypeAdapter(AgentToBridgeMessage)
_BRIDGE_MESSAGE_ADAPTER = TypeAdapter(BridgeToAgentMessage)


def encode_message(message: WireMessage) -> bytes:
    try:
        payload = message.model_dump(mode="json")
    except AttributeError as exc:
        raise TypeError("encode_message requires a protocol message model") from exc

    try:
        encoded = (
            json.dumps(
                payload,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            + b"\n"
        )
    except (TypeError, ValueError, UnicodeError) as exc:
        raise MessageValidationError("Protocol message cannot be serialized as JSON") from exc

    _check_size(len(encoded))
    return encoded


def decode_agent_message(line: bytes | str) -> AgentToBridgeMessage:
    return _decode_message(line, adapter=_AGENT_MESSAGE_ADAPTER)


def decode_bridge_message(line: bytes | str) -> BridgeToAgentMessage:
    return _decode_message(line, adapter=_BRIDGE_MESSAGE_ADAPTER)


def _decode_message[MessageT](
    line: bytes | str,
    *,
    adapter: TypeAdapter[MessageT],
) -> MessageT:
    text = _normalize_line(line)
    try:
        raw: object = json.loads(text, parse_constant=_reject_json_constant)
    except (json.JSONDecodeError, ValueError) as exc:
        raise MalformedMessageError("OCR protocol line is not valid JSON") from exc

    if not isinstance(raw, dict):
        raise MalformedMessageError("OCR protocol line must contain one JSON object")

    version = raw.get("protocol_version")
    if "protocol_version" in raw and type(version) is not int:
        raise MessageValidationError("protocol_version must be an integer")
    if type(version) is int and version not in SUPPORTED_PROTOCOL_VERSIONS:
        raise UnsupportedProtocolVersionError(
            received_version=version,
            supported_versions=SUPPORTED_PROTOCOL_VERSIONS,
        )

    try:
        return adapter.validate_json(text)
    except ValidationError as exc:
        raise MessageValidationError("OCR protocol message failed schema validation") from exc


def _normalize_line(line: bytes | str) -> str:
    if isinstance(line, bytes):
        _check_size(len(line))
        try:
            text = line.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise MalformedMessageError("OCR protocol line is not valid UTF-8") from exc
    elif isinstance(line, str):
        try:
            encoded_length = len(line.encode("utf-8", errors="strict"))
        except UnicodeEncodeError as exc:
            raise MalformedMessageError("OCR protocol line contains invalid Unicode") from exc
        _check_size(encoded_length)
        text = line
    else:
        raise TypeError("OCR protocol line must be bytes or str")

    if text.endswith("\r\n"):
        text = text[:-2]
    elif text.endswith("\n"):
        text = text[:-1]

    if not text:
        raise MalformedMessageError("OCR protocol line is empty")
    if "\n" in text or "\r" in text:
        raise MalformedMessageError("OCR protocol input must contain exactly one line")
    return text


def _check_size(actual_bytes: int) -> None:
    if actual_bytes > MAX_LINE_BYTES:
        raise MessageTooLargeError(actual_bytes=actual_bytes, max_bytes=MAX_LINE_BYTES)


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"Non-finite JSON number is not allowed: {value}")
