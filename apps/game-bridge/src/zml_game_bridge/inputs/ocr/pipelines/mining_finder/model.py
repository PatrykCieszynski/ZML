from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

FinderStatusKind = Literal["idle", "sending_probe", "searching", "found", "no_resources"]

FinderSignalKind = Literal[
    "probe_fired",
    "finder_modes_changed",
    "finder_mode_invalidated",
    "finder_units_changed",
    "finder_hit_hint",
]


def _empty_debug() -> dict[str, float]:
    return {}


@dataclass(frozen=True, slots=True)
class FinderFeatures:
    radar_signal_active: bool = False
    status_kind: FinderStatusKind | None = None
    modes_mask: int | None = None
    probes_per_drop: int | None = None
    ammo_per_drop: int | None = None
    raw_status_text: str | None = None
    raw_units_text: str | None = None
    raw_details_text: str | None = None
    hit_size_label: str | None = None
    hit_size_index: int | None = None
    resource_name: str | None = None
    range_m: float | None = None
    depth_m: float | None = None
    debug: Mapping[str, float] = field(default_factory=_empty_debug)


@dataclass(frozen=True, slots=True)
class MiningFinderSignal:
    ts_ms: int
    kind: FinderSignalKind
    modes_mask: int | None = None
    previous_modes_mask: int | None = None
    probes_per_drop: int | None = None
    ammo_per_drop: int | None = None
    raw_text: str | None = None
    raw_details_text: str | None = None
    hit_size_label: str | None = None
    hit_size_index: int | None = None
    resource_name: str | None = None
    range_m: float | None = None
    depth_m: float | None = None
    debug: Mapping[str, float] = field(default_factory=_empty_debug)
