from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from zml_backend.domain.position import WorldPos
from zml_backend.runtime.runtime_commands import RuntimeCommand


@dataclass(frozen=True, slots=True)
class MarkMiningClaimDepletedCommand(RuntimeCommand[None]):
    claim_id: str
    event_dt: datetime
    position: WorldPos
    distance_m: float = 0.0
    raw: str | None = None
    drop_id: str | None = None
    hit_id: str | None = None
    run_id: int | None = None
    segment_id: str | None = None


@dataclass(frozen=True, slots=True)
class IgnoreMiningClaimCommand(RuntimeCommand[None]):
    claim_id: str
    ignored_ts_ms: int
    reason: str | None = None
    drop_id: str | None = None
    hit_id: str | None = None
    run_id: int | None = None
    segment_id: str | None = None


@dataclass(frozen=True, slots=True)
class ExpireMiningClaimsCommand(RuntimeCommand[int]):
    now_ts_ms: int


@dataclass(frozen=True, slots=True)
class ResolvePendingDropResultsCommand(RuntimeCommand[int]):
    now_ts_ms: int
