from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from zml_game_bridge.domain.mining_events import MiningItemReceivedEvent
from zml_game_bridge.domain.money import Mpec
from zml_game_bridge.persistence.event_writer import EventWriter
from zml_game_bridge.persistence.mining_loot import MiningLootProjector, MiningLootReader
from zml_game_bridge.persistence.runs import RunStore
from zml_game_bridge.persistence.schema import ensure_schema
from zml_game_bridge.persistence.sqlite import open_sqlite


def _open_test_db(tmp_path: Path) -> sqlite3.Connection:
    conn = open_sqlite(tmp_path / "mining-loot.sqlite3")
    ensure_schema(conn)
    with conn:
        RunStore(conn).create_run(
            name="Test run",
            notes=None,
            ts_ms=1_000,
            status="running",
        )
    return conn


def test_mining_loot_projector_stores_item_received_read_model(tmp_path: Path) -> None:
    conn = _open_test_db(tmp_path)
    try:
        event_dt = datetime(2026, 1, 10, 12, 37, 50)
        env = EventWriter(conn, projector=MiningLootProjector()).write(
            MiningItemReceivedEvent(
                event_dt=event_dt,
                item_name="Blue Crystal",
                qty=8,
                value_mpec=Mpec(16_000),
                raw="raw",
                extraction_cost_mpec=Mpec(125),
                run_id=1,
            )
        )

        rows = MiningLootReader(conn).list_all(run_id=1)

        assert len(rows) == 1
        row = rows[0]
        assert row.event_id == env.event_id
        assert row.created_ts_ms == env.created_ts_ms
        assert row.event_dt == event_dt
        assert row.run_id == 1
        assert row.item_name == "Blue Crystal"
        assert row.qty == 8
        assert row.value_mpec == Mpec(16_000)
        assert row.extraction_cost_mpec == Mpec(125)
    finally:
        conn.close()
