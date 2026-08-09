from __future__ import annotations

import pytest

from zml_backend.domain.mining import ammo_cost_mpec, probe_cost_mpec
from zml_backend.domain.money import mpec_to_int


def test_ammo_cost_uses_integer_mpec_units() -> None:
    assert mpec_to_int(ammo_cost_mpec(1_000)) == 10_000


def test_probe_cost_uses_ammo_equivalent() -> None:
    assert mpec_to_int(probe_cost_mpec(2)) == 10_000


def test_mining_cost_helpers_reject_negative_quantities() -> None:
    with pytest.raises(ValueError):
        ammo_cost_mpec(-1)

    with pytest.raises(ValueError):
        probe_cost_mpec(-1)
