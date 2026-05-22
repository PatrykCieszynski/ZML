from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from zml_game_bridge.domain.mining import ammo_cost_mpec, probe_cost_mpec
from zml_game_bridge.domain.money import Mpec, mpec_to_int
from zml_game_bridge.domain.rate import Rate, multiplier, percent

DropUnitSource = Literal["ocr", "fallback", "missing"]

NO_MARKUP = multiplier("1")
FINDER_RANGE_ENHANCER_DECAY_BONUS = percent("10")
FINDER_RANGE_ENHANCER_RADIUS_BONUS = percent("1")
ZERO_MPEC: Mpec = Mpec(0)


@dataclass(frozen=True, slots=True)
class MiningToolProfile:
    name: str
    decay_mpec: Mpec
    markup: Rate = NO_MARKUP
    radius_m: float | None = None

    @property
    def marked_up_decay_mpec(self) -> Mpec:
        return apply_rate_mpec(self.decay_mpec, self.markup)


@dataclass(frozen=True, slots=True)
class FinderRangeEnhancerLoadout:
    count: int = 0
    decay_bonus_per_enhancer: Rate = FINDER_RANGE_ENHANCER_DECAY_BONUS
    radius_bonus_per_enhancer: Rate = FINDER_RANGE_ENHANCER_RADIUS_BONUS

    @property
    def extra_decay_rate(self) -> Rate:
        return self.decay_bonus_per_enhancer.times(self.count)

    @property
    def radius_multiplier(self) -> Rate:
        return NO_MARKUP.plus(self.radius_bonus_per_enhancer.times(self.count))


@dataclass(frozen=True, slots=True)
class MiningEquipmentProfile:
    finder: MiningToolProfile
    amp: MiningToolProfile | None = None
    extractor: MiningToolProfile | None = None
    finder_range_enhancers: FinderRangeEnhancerLoadout = field(
        default_factory=FinderRangeEnhancerLoadout
    )
    fallback_ammo_per_drop: int | None = None
    fallback_probes_per_drop: int | None = None


@dataclass(frozen=True, slots=True)
class DropUnitCost:
    quantity: int | None
    cost_mpec: Mpec
    source: DropUnitSource


@dataclass(frozen=True, slots=True)
class DropCostBreakdown:
    ammo: DropUnitCost
    probes: DropUnitCost
    finder_decay_mpec: Mpec
    amp_decay_mpec: Mpec
    total_mpec: Mpec
    finder_enhancer_decay_mpec: Mpec = ZERO_MPEC


def calculate_drop_cost(
    *,
    profile: MiningEquipmentProfile,
    ocr_ammo_per_drop: int | None,
    ocr_probes_per_drop: int | None,
) -> DropCostBreakdown:
    ammo, probes = _resolve_drop_unit_costs(
        profile=profile,
        ocr_ammo_per_drop=ocr_ammo_per_drop,
        ocr_probes_per_drop=ocr_probes_per_drop,
    )
    finder_decay = profile.finder.marked_up_decay_mpec
    finder_enhancer_decay = _calculate_finder_enhancer_decay_cost(profile=profile)
    amp_decay = profile.amp.marked_up_decay_mpec if profile.amp is not None else Mpec(0)

    return DropCostBreakdown(
        ammo=ammo,
        probes=probes,
        finder_decay_mpec=finder_decay,
        amp_decay_mpec=amp_decay,
        total_mpec=Mpec(
            mpec_to_int(ammo.cost_mpec)
            + mpec_to_int(probes.cost_mpec)
            + mpec_to_int(finder_decay)
            + mpec_to_int(finder_enhancer_decay)
            + mpec_to_int(amp_decay)
        ),
        finder_enhancer_decay_mpec=finder_enhancer_decay,
    )


def calculate_extraction_cost(profile: MiningEquipmentProfile) -> Mpec | None:
    if profile.extractor is None:
        return None
    return profile.extractor.marked_up_decay_mpec


def effective_finder_radius_m(profile: MiningEquipmentProfile) -> float | None:
    radius = profile.finder.radius_m
    if radius is None:
        return None
    _validate_finder_enhancer_loadout(profile.finder_range_enhancers)
    return profile.finder_range_enhancers.radius_multiplier.apply_to_float(radius)


def apply_rate_mpec(value_mpec: Mpec, rate: Rate) -> Mpec:
    value = mpec_to_int(value_mpec)
    return Mpec(rate.apply_to(value))


def _calculate_finder_enhancer_decay_cost(*, profile: MiningEquipmentProfile) -> Mpec:
    loadout = profile.finder_range_enhancers
    _validate_finder_enhancer_loadout(loadout)
    if loadout.count == 0:
        return Mpec(0)

    enhancer_decay = apply_rate_mpec(profile.finder.decay_mpec, loadout.extra_decay_rate)
    return apply_rate_mpec(enhancer_decay, profile.finder.markup)


def _validate_finder_enhancer_loadout(loadout: FinderRangeEnhancerLoadout) -> None:
    if loadout.count < 0:
        raise ValueError(f"enhancer count must be non-negative, got {loadout.count}")
    if loadout.decay_bonus_per_enhancer.ppm < 0:
        raise ValueError(
            f"enhancer decay bonus must be non-negative, got {loadout.decay_bonus_per_enhancer}"
        )
    if loadout.radius_bonus_per_enhancer.ppm < 0:
        raise ValueError(
            f"enhancer radius bonus must be non-negative, got {loadout.radius_bonus_per_enhancer}"
        )


def _resolve_drop_unit_costs(
    *,
    profile: MiningEquipmentProfile,
    ocr_ammo_per_drop: int | None,
    ocr_probes_per_drop: int | None,
) -> tuple[DropUnitCost, DropUnitCost]:
    missing = DropUnitCost(quantity=None, cost_mpec=Mpec(0), source="missing")

    if ocr_ammo_per_drop is not None:
        return (
            DropUnitCost(
                quantity=ocr_ammo_per_drop,
                cost_mpec=ammo_cost_mpec(ocr_ammo_per_drop),
                source="ocr",
            ),
            missing,
        )
    if ocr_probes_per_drop is not None:
        return (
            missing,
            DropUnitCost(
                quantity=ocr_probes_per_drop,
                cost_mpec=probe_cost_mpec(ocr_probes_per_drop),
                source="ocr",
            ),
        )
    if profile.fallback_ammo_per_drop is not None:
        return (
            DropUnitCost(
                quantity=profile.fallback_ammo_per_drop,
                cost_mpec=ammo_cost_mpec(profile.fallback_ammo_per_drop),
                source="fallback",
            ),
            missing,
        )
    if profile.fallback_probes_per_drop is not None:
        return (
            missing,
            DropUnitCost(
                quantity=profile.fallback_probes_per_drop,
                cost_mpec=probe_cost_mpec(profile.fallback_probes_per_drop),
                source="fallback",
            ),
        )
    return missing, missing
