from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from zml_game_bridge.domain.money import Mpec
from zml_game_bridge.persistence.mining_loot import (
    RECENT_LOOT_LIMIT,
    MiningLootReader,
    RecordMiningLootItemCommand,
)
from zml_game_bridge.persistence.runs import RunSegmentStore, RunStore
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
        RunSegmentStore(conn).create(
            run_id=1,
            segment_id="segment-1",
            segment_index=1,
            started_ts_ms=1_100,
            setup_hash="hash-1",
            setup_snapshot={"finder": {"name": "Finder"}},
            ts_ms=1_100,
        )
    return conn


def test_record_mining_loot_item_updates_recent_and_totals(tmp_path: Path) -> None:
    conn = _open_test_db(tmp_path)
    try:
        event_dt = datetime(2026, 1, 10, 12, 37, 50)
        with conn:
            result = RecordMiningLootItemCommand(
                event_dt=event_dt,
                item_name="Blue Crystal",
                qty=8,
                value_mpec=Mpec(16_000),
                raw="raw",
                extraction_cost_mpec=Mpec(125),
                run_id=1,
                segment_id="segment-1",
                created_ts_ms=2_000,
            ).execute(conn)
            RecordMiningLootItemCommand(
                event_dt=event_dt,
                item_name="Blue Crystal",
                qty=4,
                value_mpec=Mpec(8_000),
                raw="raw 2",
                extraction_cost_mpec=Mpec(75),
                run_id=1,
                segment_id="segment-1",
                created_ts_ms=2_500,
            ).execute(conn)

        rows = MiningLootReader(conn).list_recent(run_id=1)
        totals = MiningLootReader(conn).list_run_totals(run_id=1)
        segment_totals = MiningLootReader(conn).list_segment_totals(segment_id="segment-1")

        assert result.recent_item.event_id == 1
        assert result.recent_item.event_dt == event_dt
        assert result.recent_item.run_id == 1
        assert result.recent_item.segment_id == "segment-1"
        assert [row.qty for row in rows] == [4, 8]
        assert len(totals) == 1
        assert totals[0].scope == "run"
        assert totals[0].run_id == 1
        assert totals[0].segment_id is None
        assert totals[0].item_name == "Blue Crystal"
        assert totals[0].qty == 12
        assert totals[0].value_mpec == Mpec(24_000)
        assert totals[0].extraction_cost_mpec == Mpec(200)
        assert totals[0].event_count == 2
        assert totals[0].first_seen_ts_ms == 2_000
        assert totals[0].last_seen_ts_ms == 2_500
        assert segment_totals[0].scope == "segment"
        assert segment_totals[0].segment_id == "segment-1"
        assert segment_totals[0].qty == 12
    finally:
        conn.close()


def test_record_mining_loot_item_limits_recent_history_per_run(tmp_path: Path) -> None:
    conn = _open_test_db(tmp_path)
    try:
        event_dt = datetime(2026, 1, 10, 12, 37, 50)
        with conn:
            for idx in range(RECENT_LOOT_LIMIT + 3):
                RecordMiningLootItemCommand(
                    event_dt=event_dt,
                    item_name="Blue Crystal",
                    qty=1,
                    value_mpec=Mpec(1_000 + idx),
                    raw=f"raw {idx}",
                    extraction_cost_mpec=None,
                    run_id=1,
                    segment_id="segment-1",
                    created_ts_ms=2_000 + idx,
                ).execute(conn)

        rows = MiningLootReader(conn).list_recent(run_id=1)
        totals = MiningLootReader(conn).list_run_totals(run_id=1)

        assert len(rows) == RECENT_LOOT_LIMIT
        assert rows[0].created_ts_ms == 2_000 + RECENT_LOOT_LIMIT + 2
        assert rows[-1].created_ts_ms == 2_000 + 3
        assert totals[0].event_count == RECENT_LOOT_LIMIT + 3
        assert totals[0].qty == RECENT_LOOT_LIMIT + 3
    finally:
        conn.close()
