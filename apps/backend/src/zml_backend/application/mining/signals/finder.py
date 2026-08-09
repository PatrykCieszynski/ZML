from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from zml_backend.domain.position import WorldPos
from zml_backend.events.base import SignalBase


def _empty_debug() -> dict[str, float]:
    return {}


@dataclass(frozen=True, slots=True)
class ProbeFiredSignal(SignalBase):
    ts_ms: int
    position: WorldPos | None
    modes_mask: int | None
    probes_per_drop: int | None = None
    ammo_per_drop: int | None = None
    raw_status_text: str | None = None
    roi_name: str = "finder_mvp_bottom_left"
    debug: Mapping[str, float] = field(default_factory=_empty_debug)


@dataclass(frozen=True, slots=True)
class FinderModesChangedSignal(SignalBase):
    ts_ms: int
    modes_mask: int
    previous_modes_mask: int | None
    roi_name: str = "finder_mvp_bottom_left"
    debug: Mapping[str, float] = field(default_factory=_empty_debug)


@dataclass(frozen=True, slots=True)
class FinderModeInvalidatedSignal(SignalBase):
    ts_ms: int
    previous_modes_mask: int | None
    roi_name: str = "finder_mvp_bottom_left"
    debug: Mapping[str, float] = field(default_factory=_empty_debug)


@dataclass(frozen=True, slots=True)
class FinderUnitsChangedSignal(SignalBase):
    ts_ms: int
    probes_per_drop: int | None
    ammo_per_drop: int | None
    raw_text: str | None = None
    roi_name: str = "finder_mvp_bottom_left"


@dataclass(frozen=True, slots=True)
class FinderHitHintSignal(SignalBase):
    ts_ms: int
    size_label: str
    size_index: int
    resource_name: str
    range_m: float | None = None
    depth_m: float | None = None
    raw_status_text: str | None = None
    raw_details_text: str | None = None
    roi_name: str = "finder_mvp_bottom_left"


@dataclass(frozen=True, slots=True)
class FinderNoResourcesSignal(SignalBase):
    ts_ms: int
    raw_status_text: str | None = None
    roi_name: str = "finder_mvp_bottom_left"
