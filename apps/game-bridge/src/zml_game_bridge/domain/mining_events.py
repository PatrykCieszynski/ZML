from __future__ import annotations

from dataclasses import dataclass

from zml_game_bridge.domain.mining_cost import DropCostBreakdown
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
