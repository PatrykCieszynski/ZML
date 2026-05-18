from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WorldPos:
    planet_name: str | None
    x: int
    y: int
    z: int | None