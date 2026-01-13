from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from zml_game_bridge.common.types import Mpec
from zml_game_bridge.events.base import EventBase
from zml_game_bridge.inputs.chat.model import ChannelType


@dataclass(frozen=True, slots=True)
class ChatEventBase(EventBase):
    event_dt: datetime
    channel_type: ChannelType
    channel_token: str
    raw: str


@dataclass(frozen=True, slots=True)
class ResourceClaimed(ChatEventBase):
    resource_name: str


@dataclass(frozen=True, slots=True)
class ItemReceived(ChatEventBase):
    item_name: str
    qty: int
    value_mpec: Mpec


@dataclass(frozen=True, slots=True)
class ResourceDepleted(ChatEventBase):
    pass


@dataclass(frozen=True, slots=True)
class EnhancerBroke(ChatEventBase):
    enhancer_name: str
    item_name: str
    remaining: int


@dataclass(frozen=True, slots=True)
class PositionPing(ChatEventBase):
    planet_name: str
    x: int
    y: int
    z: int


@dataclass(frozen=True, slots=True)
class SkillGained(ChatEventBase):
    skill: str
    amount: Decimal
