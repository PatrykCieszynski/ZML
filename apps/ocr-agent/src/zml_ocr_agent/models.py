from __future__ import annotations

from dataclasses import dataclass
from enum import IntFlag


class MiningMode(IntFlag):
    NONE = 0
    ORE = 1
    ENMATTER = 2
    TREASURE = 4


@dataclass(frozen=True, slots=True)
class WorldPosition:
    planet_name: str | None
    x: int
    y: int
    z: int | None
