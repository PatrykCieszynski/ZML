from __future__ import annotations

import re
from datetime import datetime

from zml_game_bridge.inputs.chat.model import ChannelType, ChatLine

# Example:
# 2026-01-10 12:37:50 [System] [] You have claimed a resource! (Yellow Crystal)
_HEADER_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"\[(?P<channel>[^\]]*)\] "
    r"\[(?P<speaker>[^\]]*)\] "
    r"(?P<msg>.*)$"
)


def classify_channel(channel_token: str) -> ChannelType:
    if channel_token == "System":
        return ChannelType.SYSTEM
    if channel_token == "Globals":
        return ChannelType.GLOBALS
    if channel_token.startswith("#"):
        return ChannelType.PUBLIC
    return ChannelType.UNKNOWN


def parse_chat_line(raw_line: str) -> ChatLine | None:
    raw = raw_line.rstrip("\r\n")
    m = _HEADER_RE.fullmatch(raw)
    if not m:
        return None

    ts_str = m.group("ts")
    channel_token = m.group("channel").strip()
    speaker = m.group("speaker").strip()
    msg = m.group("msg").strip()

    try:
        event_dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None

    return ChatLine(
        event_dt=event_dt,
        channel_type=classify_channel(channel_token),
        channel_token=channel_token,
        speaker=speaker,
        message=msg,
        raw=raw,
    )
