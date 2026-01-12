from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ChannelType(str, Enum):
    SYSTEM = "System"
    GLOBALS = "Globals"
    PUBLIC = "Public"
    UNKNOWN = "Unknown"


@dataclass(frozen=True, slots=True)
class ChatLine:
    event_dt: datetime  # naive dt from log line (EU time)
    channel_type: ChannelType
    channel_token: str  # raw token from [] e.g. "System", "#calytrade", "Rookie"
    speaker: str  # raw speaker token (can be empty)
    message: str  # raw payload
    raw: str  # original line (single line only)
