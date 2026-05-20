from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from zml_game_bridge.domain.mining import ammo_cost_mpec, probe_cost_mpec
from zml_game_bridge.domain.money import Mpec, mpec_to_int

MarkupBps = int
DropUnitSource = Literal["ocr", "fallback", "missing"]

FULL_MARKUP_BPS: MarkupBps = 10_000


@dataclass(frozen=True, slots=True)
class MiningToolProfile:
    name: str
    decay_mpec: Mpec
    markup_bps: MarkupBps = FULL_MARKUP_BPS
    radius_m: float | None = None

    @property
    def marked_up_decay_mpec(self) -> Mpec:
        return apply_markup_mpec(self.decay_mpec, self.markup_bps)


@dataclass(frozen=True, slots=True)
class MiningEquipmentProfile:
    finder: MiningToolProfile
    amp: MiningToolProfile | None = None
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
            + mpec_to_int(amp_decay)
        ),
    )


def apply_markup_mpec(value_mpec: Mpec, markup_bps: MarkupBps) -> Mpec:
    value = mpec_to_int(value_mpec)
    if value < 0:
        raise ValueError(f"value_mpec must be non-negative, got {value_mpec}")
    if markup_bps < 0:
        raise ValueError(f"markup_bps must be non-negative, got {markup_bps}")
    return Mpec((value * markup_bps + FULL_MARKUP_BPS // 2) // FULL_MARKUP_BPS)


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
