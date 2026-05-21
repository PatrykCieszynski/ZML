from __future__ import annotations

from zml_game_bridge.domain.rate import multiplier, percent


def test_percent_creates_readable_integer_backed_rates() -> None:
    rate = percent("125")

    assert rate.apply_to(100) == 125


def test_multiplier_creates_readable_integer_backed_rates() -> None:
    rate = multiplier("1.25")

    assert rate.apply_to(100) == 125


def test_rate_apply_to_uses_half_up_rounding() -> None:
    assert percent("105").apply_to(123) == 129


def test_rate_can_be_added_and_repeated_for_tool_bonuses() -> None:
    rate = multiplier("1").plus(percent("1").times(2))

    assert rate.apply_to_float(55.0) == 56.1


def test_rate_rejects_invalid_values() -> None:
    try:
        percent("abc")
    except ValueError as exc:
        assert "Invalid rate value" in str(exc)
    else:
        raise AssertionError("Expected invalid rate value")
