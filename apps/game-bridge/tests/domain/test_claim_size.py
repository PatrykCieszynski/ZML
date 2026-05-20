from __future__ import annotations

from zml_game_bridge.domain.claim_size import (
    expected_claim_expires_ts_ms,
    get_claim_size_tier,
)


def test_claim_size_tier_prefers_size_index() -> None:
    tier = get_claim_size_tier(size_index=9, size_label="Minimal")

    assert tier is not None
    assert tier.name == "Ample"
    assert tier.expires_hours == 2


def test_claim_size_tier_falls_back_to_normalized_label() -> None:
    tier = get_claim_size_tier(size_index=None, size_label="  very   poor ")

    assert tier is not None
    assert tier.level == 3
    assert tier.expires_hours == 1


def test_expected_claim_expires_ts_ms_uses_tier_expiry_hours() -> None:
    assert (
        expected_claim_expires_ts_ms(
            observed_ts_ms=2_000,
            size_index=10,
            size_label="Considerable",
        )
        == 10_802_000
    )


def test_expected_claim_expires_ts_ms_returns_none_for_non_expiring_tier() -> None:
    assert (
        expected_claim_expires_ts_ms(
            observed_ts_ms=2_000,
            size_index=23,
            size_label="Rich",
        )
        is None
    )
