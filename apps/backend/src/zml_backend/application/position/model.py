from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from zml_backend.domain.position import WorldPos

PositionSource = Literal["ocr", "chat", "manual"]
PositionDecisionKind = Literal[
    "accepted",
    "rejected_outlier",
    "suspect_relocation",
    "relocation_accepted",
    "trusted_reset",
    "stale_rejected",
]


@dataclass(frozen=True, slots=True)
class PositionSnapshot:
    observed_ts_ms: int
    received_ts_ms: int
    position: WorldPos
    source: PositionSource
    confidence: float | None = None
    sequence_id: int | None = None


@dataclass(frozen=True, slots=True)
class PositionTrackingConfig:
    outlier_filter_enabled: bool = True
    max_jump_m: float = 150.0
    max_speed_mps: float = 120.0
    relocation_confirm_s: float = 5.0
    relocation_min_samples: int = 10
    relocation_cluster_radius_m: float = 100.0
    history_window_s: float = 15.0
    history_max_samples: int = 60


@dataclass(frozen=True, slots=True)
class PositionDecision:
    kind: PositionDecisionKind
    snapshot: PositionSnapshot | None
    reason: str
    stable_snapshot: PositionSnapshot | None = None
    distance_m: float | None = None
    allowed_m: float | None = None
    candidate_samples: int = 0
    candidate_age_s: float | None = None

    @property
    def accepted(self) -> bool:
        return self.snapshot is not None and self.kind in {
            "accepted",
            "relocation_accepted",
            "trusted_reset",
        }
