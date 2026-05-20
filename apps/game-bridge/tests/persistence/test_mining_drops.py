from __future__ import annotations

import sqlite3
from pathlib import Path

from zml_game_bridge.domain.mining_cost import DropCostBreakdown, DropUnitCost
from zml_game_bridge.domain.mining_events import (
    MiningDropEvent,
    MiningHitHintEvent,
    MiningNoResourcesEvent,
)
from zml_game_bridge.domain.money import Mpec
from zml_game_bridge.domain.position import WorldPos
from zml_game_bridge.persistence.event_writer import EventWriter
from zml_game_bridge.persistence.mining_drops import MiningDropProjector, MiningDropReader
from zml_game_bridge.persistence.schema import ensure_schema
from zml_game_bridge.persistence.sqlite import open_sqlite


def _open_test_db(tmp_path: Path) -> sqlite3.Connection:
    conn = open_sqlite(tmp_path / "mining-drops.sqlite3")
    ensure_schema(conn)
    return conn


def test_mining_drop_projector_stores_drop_read_model(tmp_path: Path) -> None:
    conn = _open_test_db(tmp_path)
    try:
        writer = EventWriter(conn, projector=MiningDropProjector())

        writer.write(_drop_event(drop_id="drop-1"))

        row = MiningDropReader(conn).get("drop-1")
        assert row is not None
        assert row.drop_id == "drop-1"
        assert row.observed_ts_ms == 1_000
        assert row.position == WorldPos(planet_name="Calypso", x=58_890, y=84_639, z=None)
        assert row.drop_radius_m == 54.0
        assert row.modes_mask == 1
        assert row.ammo_per_drop == 1_000
        assert row.total_cost_mpec == 10_100
        assert row.result == "pending"
        assert row.resource_name is None
    finally:
        conn.close()


def test_mining_drop_projector_marks_hit_result(tmp_path: Path) -> None:
    conn = _open_test_db(tmp_path)
    try:
        writer = EventWriter(conn, projector=MiningDropProjector())

        writer.write(_drop_event(drop_id="drop-1"))
        hit_env = writer.write(
            MiningHitHintEvent(
                hit_id="hit-1",
                drop_id="drop-1",
                observed_ts_ms=2_000,
                position=WorldPos(planet_name="Calypso", x=58_890, y=84_639, z=None),
                size_label="Minimal",
                size_index=1,
                resource_name="Lysterium Stone",
                range_m=51.14,
                depth_m=53.0,
            )
        )

        row = MiningDropReader(conn).get("drop-1")
        assert row is not None
        assert row.result == "hit"
        assert row.result_event_id == hit_env.event_id
        assert row.result_observed_ts_ms == 2_000
        assert row.hit_id == "hit-1"
        assert row.resource_name == "Lysterium Stone"
        assert row.size_label == "Minimal"
        assert row.size_index == 1
        assert row.range_m == 51.14
        assert row.depth_m == 53.0
    finally:
        conn.close()


def test_mining_drop_projector_marks_no_resources_result(tmp_path: Path) -> None:
    conn = _open_test_db(tmp_path)
    try:
        writer = EventWriter(conn, projector=MiningDropProjector())

        writer.write(_drop_event(drop_id="drop-1"))
        no_resources_env = writer.write(
            MiningNoResourcesEvent(
                drop_id="drop-1",
                observed_ts_ms=2_000,
                position=WorldPos(planet_name="Calypso", x=58_890, y=84_639, z=None),
            )
        )

        row = MiningDropReader(conn).get("drop-1")
        assert row is not None
        assert row.result == "no_resources"
        assert row.result_event_id == no_resources_env.event_id
        assert row.result_observed_ts_ms == 2_000
        assert row.hit_id is None
        assert row.resource_name is None
    finally:
        conn.close()


def test_mining_drop_projector_ignores_unlinked_result(tmp_path: Path) -> None:
    conn = _open_test_db(tmp_path)
    try:
        writer = EventWriter(conn, projector=MiningDropProjector())

        writer.write(
            MiningNoResourcesEvent(
                drop_id=None,
                observed_ts_ms=2_000,
                position=None,
            )
        )

        assert MiningDropReader(conn).list_since(since_ts_ms=0) == []
    finally:
        conn.close()


def _drop_event(*, drop_id: str) -> MiningDropEvent:
    return MiningDropEvent(
        drop_id=drop_id,
        observed_ts_ms=1_000,
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
        drop_radius_m=54.0,
    )
