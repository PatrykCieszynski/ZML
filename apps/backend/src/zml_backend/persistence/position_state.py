from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from zml_backend.persistence.sqlite import open_read_connection

LAST_KNOWN_PLANET_KEY: Final[str] = "last_known_planet"


@dataclass(frozen=True, slots=True)
class SetLastKnownPlanetCommand:
    planet_name: str

    def execute(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            INSERT OR REPLACE INTO app_state(key, value)
            VALUES (?, ?)
            """,
            (LAST_KNOWN_PLANET_KEY, self.planet_name),
        )


def load_last_known_planet(db_path: Path | str) -> str | None:
    path = Path(db_path)
    if not path.exists():
        return None

    try:
        conn = open_read_connection(path)
    except sqlite3.OperationalError:
        return None

    try:
        try:
            row = conn.execute(
                "SELECT value FROM app_state WHERE key = ?",
                (LAST_KNOWN_PLANET_KEY,),
            ).fetchone()
        except sqlite3.OperationalError:
            return None
    finally:
        conn.close()

    if row is None:
        return None
    value = str(row["value"]).strip()
    return value or None
