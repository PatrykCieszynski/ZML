from __future__ import annotations

from zml_game_bridge.domain.mining_cost import (
    FULL_MARKUP_BPS,
    MiningEquipmentProfile,
    MiningToolProfile,
    apply_markup_mpec,
    calculate_drop_cost,
)
from zml_game_bridge.domain.money import Mpec, mpec_to_int


def test_calculate_drop_cost_prefers_ocr_units_over_profile_fallbacks() -> None:
    profile = MiningEquipmentProfile(
        finder=MiningToolProfile(name="Finder", decay_mpec=Mpec(123), markup_bps=10_500),
        amp=MiningToolProfile(name="Amp", decay_mpec=Mpec(2_000), markup_bps=12_500),
        fallback_ammo_per_drop=500,
        fallback_probes_per_drop=1,
    )

    cost = calculate_drop_cost(
        profile=profile,
        ocr_ammo_per_drop=1_000,
        ocr_probes_per_drop=None,
    )

    assert cost.ammo.quantity == 1_000
    assert mpec_to_int(cost.ammo.cost_mpec) == 10_000
    assert cost.ammo.source == "ocr"
    assert cost.probes.quantity is None
    assert mpec_to_int(cost.probes.cost_mpec) == 0
    assert cost.probes.source == "missing"
    assert mpec_to_int(cost.finder_decay_mpec) == 129
    assert mpec_to_int(cost.amp_decay_mpec) == 2_500
    assert mpec_to_int(cost.total_mpec) == 12_629


def test_calculate_drop_cost_uses_profile_fallbacks_when_ocr_units_are_missing() -> None:
    profile = MiningEquipmentProfile(
        finder=MiningToolProfile(name="Finder", decay_mpec=Mpec(100)),
        fallback_ammo_per_drop=500,
        fallback_probes_per_drop=1,
    )

    cost = calculate_drop_cost(
        profile=profile,
        ocr_ammo_per_drop=None,
        ocr_probes_per_drop=None,
    )

    assert cost.ammo.quantity == 500
    assert mpec_to_int(cost.ammo.cost_mpec) == 5_000
    assert cost.ammo.source == "fallback"
    assert cost.probes.quantity is None
    assert mpec_to_int(cost.probes.cost_mpec) == 0
    assert cost.probes.source == "missing"
    assert mpec_to_int(cost.finder_decay_mpec) == 100
    assert mpec_to_int(cost.amp_decay_mpec) == 0
    assert mpec_to_int(cost.total_mpec) == 5_100


def test_calculate_drop_cost_uses_probe_count_when_ammo_units_are_missing() -> None:
    profile = MiningEquipmentProfile(
        finder=MiningToolProfile(name="Finder", decay_mpec=Mpec(100)),
        fallback_ammo_per_drop=500,
        fallback_probes_per_drop=1,
    )

    cost = calculate_drop_cost(
        profile=profile,
        ocr_ammo_per_drop=None,
        ocr_probes_per_drop=2,
    )

    assert cost.ammo.quantity is None
    assert mpec_to_int(cost.ammo.cost_mpec) == 0
    assert cost.ammo.source == "missing"
    assert cost.probes.quantity == 2
    assert mpec_to_int(cost.probes.cost_mpec) == 10_000
    assert cost.probes.source == "ocr"
    assert mpec_to_int(cost.total_mpec) == 10_100


def test_calculate_drop_cost_marks_missing_units_without_blocking_decay_cost() -> None:
    profile = MiningEquipmentProfile(
        finder=MiningToolProfile(name="Finder", decay_mpec=Mpec(100)),
    )

    cost = calculate_drop_cost(
        profile=profile,
        ocr_ammo_per_drop=None,
        ocr_probes_per_drop=None,
    )

    assert cost.ammo.quantity is None
    assert mpec_to_int(cost.ammo.cost_mpec) == 0
    assert cost.ammo.source == "missing"
    assert cost.probes.quantity is None
    assert mpec_to_int(cost.probes.cost_mpec) == 0
    assert cost.probes.source == "missing"
    assert mpec_to_int(cost.total_mpec) == 100


def test_apply_markup_mpec_uses_basis_points_with_half_up_mpec_rounding() -> None:
    assert mpec_to_int(apply_markup_mpec(Mpec(100), FULL_MARKUP_BPS)) == 100
    assert mpec_to_int(apply_markup_mpec(Mpec(123), 10_500)) == 129
