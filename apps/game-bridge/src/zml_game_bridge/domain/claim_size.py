from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ClaimSizeTier:
    name: str
    level: int
    expires_hours: int | None


CLAIM_SIZE_TIERS: tuple[ClaimSizeTier, ...] = (
    ClaimSizeTier("Minimal", 1, 1),
    ClaimSizeTier("Tiny", 2, 1),
    ClaimSizeTier("Very Poor", 3, 1),
    ClaimSizeTier("Poor", 4, 1),
    ClaimSizeTier("Small", 5, 1),
    ClaimSizeTier("Modest", 6, 1),
    ClaimSizeTier("Average", 7, 1),
    ClaimSizeTier("Medium", 8, 1),
    ClaimSizeTier("Ample", 9, 2),
    ClaimSizeTier("Considerable", 10, 3),
    ClaimSizeTier("Sizable", 11, 6),
    ClaimSizeTier("Large", 12, 10),
    ClaimSizeTier("Abundant", 13, 18),
    ClaimSizeTier("Great", 14, 24),
    ClaimSizeTier("Substantial", 15, 24),
    ClaimSizeTier("Significant", 16, 24),
    ClaimSizeTier("Plentiful", 17, 36),
    ClaimSizeTier("Huge", 18, 36),
    ClaimSizeTier("Extremely Large", 19, 48),
    ClaimSizeTier("Massive", 20, 72),
    ClaimSizeTier("Vast", 21, 96),
    ClaimSizeTier("Enormous", 22, 120),
    ClaimSizeTier("Rich", 23, None),
    ClaimSizeTier("Gigantic", 24, None),
    ClaimSizeTier("Mammoth", 25, None),
    ClaimSizeTier("Colossal", 26, None),
    ClaimSizeTier("Immense", 27, None),
)

_CLAIM_SIZE_BY_LEVEL = {tier.level: tier for tier in CLAIM_SIZE_TIERS}


def _normalize_claim_size_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


_CLAIM_SIZE_BY_NAME = {_normalize_claim_size_name(tier.name): tier for tier in CLAIM_SIZE_TIERS}


def get_claim_size_tier(*, size_index: int | None, size_label: str | None) -> ClaimSizeTier | None:
    if size_index is not None:
        return _CLAIM_SIZE_BY_LEVEL.get(size_index)
    if not size_label:
        return None
    return _CLAIM_SIZE_BY_NAME.get(_normalize_claim_size_name(size_label))


def expected_claim_expires_ts_ms(
    *,
    observed_ts_ms: int,
    size_index: int | None,
    size_label: str | None,
) -> int | None:
    tier = get_claim_size_tier(size_index=size_index, size_label=size_label)
    if tier is None or tier.expires_hours is None:
        return None
    return observed_ts_ms + tier.expires_hours * 60 * 60 * 1000
