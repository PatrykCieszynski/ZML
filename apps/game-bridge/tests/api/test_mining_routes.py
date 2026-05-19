from __future__ import annotations

import sqlite3
from pathlib import Path

from zml_game_bridge.api.routes.mining import list_mining_drops
from zml_game_bridge.domain.mining_cost import DropCostBreakdown, DropUnitCost
from zml_game_bridge.domain.mining_events import MiningDropEvent
from zml_game_bridge.domain.money import Mpec
from zml_game_bridge.domain.position import WorldPos
from zml_game_bridge.persistence.event_writer import EventWriter
from zml_game_bridge.persistence.mining_drops import MiningDropProjector
from zml_game_bridge.persistence.schema import ensure_schema
from zml_game_bridge.persistence.sqlite import open_sqlite


def _open_test_db(tmp_path: Path) -> sqlite3.Connection:
    conn = open_sqlite(tmp_path / "mining-routes.sqlite3")
    ensure_schema(conn)
    return conn


def test_list_mining_drops_returns_drops_from_window(
    monkeypatch,
    tmp_path: Path,
) -> None:
    conn = _open_test_db(tmp_path)
    try:
        EventWriter(conn, projector=MiningDropProjector()).write(
            _drop_event(
                drop_id="drop-1",
                observed_ts_ms=1_000,
            )
        )
        EventWriter(conn, projector=MiningDropProjector()).write(
            _drop_event(
                drop_id="drop-2",
                observed_ts_ms=2_000,
            )
        )

        monkeypatch.setattr("zml_game_bridge.api.routes.mining._now_ms", lambda: 3_000)

        drops = list_mining_drops(conn, window_minutes=1)

        assert [drop.drop_id for drop in drops] == ["drop-2", "drop-1"]
        assert drops[0].position is not None
        assert drops[0].position.x == 58_890
        assert drops[0].cost.total_mpec == 10_100
        assert drops[0].result == "pending"
    finally:
        conn.close()


def test_list_mining_drops_filters_out_older_drops(monkeypatch, tmp_path: Path) -> None:
    conn = _open_test_db(tmp_path)
    try:
        EventWriter(conn, projector=MiningDropProjector()).write(
            _drop_event(
                drop_id="old-drop",
                observed_ts_ms=1_000,
            )
        )
        EventWriter(conn, projector=MiningDropProjector()).write(
            _drop_event(
                drop_id="fresh-drop",
                observed_ts_ms=65_000,
            )
        )

        monkeypatch.setattr("zml_game_bridge.api.routes.mining._now_ms", lambda: 120_000)

        drops = list_mining_drops(conn, window_minutes=1)

        assert [drop.drop_id for drop in drops] == ["fresh-drop"]
    finally:
        conn.close()


def _drop_event(*, drop_id: str, observed_ts_ms: int) -> MiningDropEvent:
    return MiningDropEvent(
        drop_id=drop_id,
        observed_ts_ms=observed_ts_ms,
        position=WorldPos(planet_name="Calypso", x=58_890, y=84_639, z=None),
        modes_mask=1,
        probes_per_drop=None,
        ammo_per_drop=1_000,
        cost=DropCostBreakdown(
            ammo=DropUnitCost(quantity=1_000, cost_mpec=Mpec(10_000), source="ocr"),
            probes=DropUnitCost(quantity=None, cost_mpec=Mpec(0), source="missing"),
            finder_decay_mpec=Mpec(100),
            amp_decay_mpec=Mpec(0),
            total_mpec=Mpec(10_100),
        ),
    )
