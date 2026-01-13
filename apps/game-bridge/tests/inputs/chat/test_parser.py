from __future__ import annotations

from datetime import datetime

import pytest

from zml_game_bridge.inputs.chat.model import ChannelType
from zml_game_bridge.inputs.chat.parser import classify_channel, parse_chat_line


def test_classify_channel_system() -> None:
    assert classify_channel("System") == ChannelType.SYSTEM


def test_classify_channel_globals() -> None:
    assert classify_channel("Globals") == ChannelType.GLOBALS


def test_classify_channel_public_hash() -> None:
    assert classify_channel("#cyrenetrade") == ChannelType.PUBLIC


def test_classify_channel_unknown() -> None:
    assert classify_channel("Rookie") == ChannelType.UNKNOWN


def test_parse_chat_line_system_with_empty_speaker() -> None:
    raw = "2026-01-10 12:37:50 [System] [] You have claimed a resource! (Yellow Crystal)"
    line = parse_chat_line(raw)
    assert line is not None
    assert line.event_dt == datetime(2026, 1, 10, 12, 37, 50)
    assert line.channel_token == "System"
    assert line.channel_type == ChannelType.SYSTEM
    assert line.speaker == ""
    assert line.message == "You have claimed a resource! (Yellow Crystal)"
    assert line.raw == raw


def test_parse_chat_line_strips_newline_and_message() -> None:
    raw = "2026-01-10 12:37:50 [System] []   This resource is depleted  \r\n"
    line = parse_chat_line(raw)
    assert line is not None
    assert line.raw == "2026-01-10 12:37:50 [System] []   This resource is depleted  "
    assert line.message == "This resource is depleted"


def test_parse_chat_line_returns_none_for_non_header() -> None:
    assert parse_chat_line("some continuation line...") is None


@pytest.mark.parametrize(
    "raw",
    [
        "",  # empty
        "2026-01-10 [System] [] msg",  # bad timestamp
        "2026-01-10 12:00:00 System [] msg",  # missing brackets
        "2026-99-99 12:00:00 [System] [] msg",  # invalid date
    ],
)
def test_parse_chat_line_returns_none_for_invalid(raw: str) -> None:
    assert parse_chat_line(raw) is None


def test_parse_chat_line_public_channel() -> None:
    raw = "2026-01-10 12:37:50 [#cyrenetrade] [Zabu] WTS stuff"
    line = parse_chat_line(raw)
    assert line is not None
    assert line.channel_type == ChannelType.PUBLIC
    assert line.channel_token == "#cyrenetrade"
    assert line.speaker == "Zabu"
    assert line.message == "WTS stuff"
