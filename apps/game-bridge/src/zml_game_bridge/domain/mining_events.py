from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from zml_game_bridge.domain.mining_cost import DropCostBreakdown
from zml_game_bridge.domain.money import Mpec
from zml_game_bridge.domain.position import WorldPos
from zml_game_bridge.events.base import EventBase


@dataclass(frozen=True, slots=True)
class MiningDropEvent(EventBase):
    drop_id: str
    observed_ts_ms: int
    position: WorldPos | None
    modes_mask: int | None
    probes_per_drop: int | None
    ammo_per_drop: int | None
    cost: DropCostBreakdown
    drop_radius_m: float | None = None
    raw_status_text: str | None = None


@dataclass(frozen=True, slots=True)
class MiningHitHintEvent(EventBase):
    # TODO: This is only the finder-visible preclaim hint. The actual deeds can
    # arrive through chat/deed OCR at the same timestamp, and one multi-mode drop
    # can produce multiple deeds even though the finder shows a single hint.
    hit_id: str
    drop_id: str | None
    observed_ts_ms: int
    position: WorldPos | None
    size_label: str
    size_index: int
    resource_name: str
    expected_expires_ts_ms: int | None = None
    range_m: float | None = None
    depth_m: float | None = None
    raw_status_text: str | None = None
    raw_details_text: str | None = None


@dataclass(frozen=True, slots=True)
class MiningNoResourcesEvent(EventBase):
    drop_id: str | None
    observed_ts_ms: int
    position: WorldPos | None
    raw_status_text: str | None = None


@dataclass(frozen=True, slots=True)
class MiningClaimCreatedEvent(EventBase):
    claim_id: str
    hit_id: str | None
    drop_id: str | None
    observed_ts_ms: int
    position: WorldPos | None
    search_radius_m: float | None
    resource_name: str | None
    size_label: str | None
    size_index: int | None
    expected_expires_ts_ms: int | None
    range_m: float | None = None
    depth_m: float | None = None


@dataclass(frozen=True, slots=True)
class MiningItemReceivedEvent(EventBase):
    event_dt: datetime
    item_name: str
    qty: int
    value_mpec: Mpec
    raw: str


@dataclass(frozen=True, slots=True)
class MiningClaimDeedReceivedEvent(EventBase):
    event_dt: datetime
    resource_name: str
    mining_type: str | None
    deed_item_name: str | None
    qty: int | None
    value_mpec: Mpec | None
    raw: str
    received_raw: str | None = None
    claimed_raw: str | None = None


@dataclass(frozen=True, slots=True)
class MiningClaimDepletedEvent(EventBase):
    claim_id: str
    drop_id: str | None
    hit_id: str | None
    event_dt: datetime
    position: WorldPos
    distance_m: float
    raw: str


@dataclass(frozen=True, slots=True)
class MiningEnhancerBrokeEvent(EventBase):
    event_dt: datetime
    enhancer_name: str
    item_name: str
    remaining: int
    raw: str
