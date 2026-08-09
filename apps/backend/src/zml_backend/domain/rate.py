from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Self

_PPM_SCALE = 1_000_000


@dataclass(frozen=True, slots=True)
class Rate:
    ppm: int

    @classmethod
    def percent(cls, value: str) -> Self:
        decimal = _parse_decimal(value)
        ppm = int((decimal * Decimal("10000")).to_integral_value(rounding=ROUND_HALF_UP))
        return cls(ppm)

    @classmethod
    def multiplier(cls, value: str) -> Self:
        decimal = _parse_decimal(value)
        ppm = int((decimal * Decimal(str(_PPM_SCALE))).to_integral_value(rounding=ROUND_HALF_UP))
        return cls(ppm)

    def apply_to(self, value: int) -> int:
        if value < 0:
            raise ValueError(f"value must be non-negative, got {value}")
        if self.ppm < 0:
            raise ValueError(f"rate must be non-negative, got {self.ppm}")
        return (value * self.ppm + _PPM_SCALE // 2) // _PPM_SCALE

    def apply_to_float(self, value: float) -> float:
        if value < 0:
            raise ValueError(f"value must be non-negative, got {value}")
        if self.ppm < 0:
            raise ValueError(f"rate must be non-negative, got {self.ppm}")
        return value * self.ppm / _PPM_SCALE

    def plus(self, other: Rate) -> Rate:
        return Rate(self.ppm + other.ppm)

    def times(self, count: int) -> Rate:
        return Rate(self.ppm * count)


def percent(value: str) -> Rate:
    return Rate.percent(value)


def multiplier(value: str) -> Rate:
    return Rate.multiplier(value)


def _parse_decimal(value: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid rate value: {value!r}") from exc
