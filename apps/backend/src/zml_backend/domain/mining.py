from __future__ import annotations

from enum import IntFlag

from zml_backend.domain.money import Mpec, mpec_to_int


class MiningMode(IntFlag):
    NONE = 0
    ORE = 1
    ENMATTER = 2
    TREASURE = 4


AMMO_PER_PROBE = 500
AMMO_UNIT_COST_MPEC = Mpec(10)
PROBE_COST_MPEC = Mpec(AMMO_PER_PROBE * mpec_to_int(AMMO_UNIT_COST_MPEC))


def ammo_cost_mpec(ammo_units: int) -> Mpec:
    if ammo_units < 0:
        raise ValueError(f"ammo_units must be non-negative, got {ammo_units}")
    return Mpec(ammo_units * mpec_to_int(AMMO_UNIT_COST_MPEC))


def probe_cost_mpec(probes: int) -> Mpec:
    if probes < 0:
        raise ValueError(f"probes must be non-negative, got {probes}")
    return Mpec(probes * mpec_to_int(PROBE_COST_MPEC))
