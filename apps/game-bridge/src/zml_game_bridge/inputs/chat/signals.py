from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from zml_game_bridge.domain.money import Mpec
from zml_game_bridge.domain.position import WorldPos
from zml_game_bridge.events.base import SignalBase
from zml_game_bridge.inputs.chat.model import ChannelType


@dataclass(frozen=True, slots=True)
class ChatSignalBase(SignalBase):
    event_dt: datetime
    channel_type: ChannelType
    channel_token: str
    raw: str


@dataclass(frozen=True, slots=True)
class ResourceClaimedSignal(ChatSignalBase):
    resource_name: str


@dataclass(frozen=True, slots=True)
class ItemReceivedSignal(ChatSignalBase):
    item_name: str
    qty: int
    value_mpec: Mpec


@dataclass(frozen=True, slots=True)
class ResourceDepletedSignal(ChatSignalBase):
    pass


@dataclass(frozen=True, slots=True)
class EnhancerBrokeSignal(ChatSignalBase):
    enhancer_name: str
    item_name: str
    remaining: int


@dataclass(frozen=True, slots=True)
class PlayerPosWaypointSignal(ChatSignalBase):
    position: WorldPos


@dataclass(frozen=True, slots=True)
class SkillGainedSignal(ChatSignalBase):
    skill: str
    amount: Decimal
