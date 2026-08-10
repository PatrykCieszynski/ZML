from __future__ import annotations

from zml_backend.persistence.position_state import (
    SetLastKnownPlanetCommand,
    load_last_known_planet,
)
from zml_backend.persistence.schema import ensure_schema
from zml_backend.persistence.sqlite import open_writer_connection


def test_position_state_round_trip(tmp_path) -> None:
    db_path = tmp_path / "zml.sqlite3"
    conn = open_writer_connection(db_path)
    try:
        ensure_schema(conn)
        assert load_last_known_planet(db_path) is None

        SetLastKnownPlanetCommand(planet_name="Calypso").execute(conn)
        conn.commit()
    finally:
        conn.close()

    assert load_last_known_planet(db_path) == "Calypso"
