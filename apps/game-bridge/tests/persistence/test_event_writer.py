from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import ClassVar

from zml_game_bridge.domain.mining_events import (
    MiningClaimDeedReceivedEvent,
    MiningItemReceivedEvent,
)
from zml_game_bridge.domain.money import Mpec
from zml_game_bridge.events.base import EventBase
from zml_game_bridge.events.envelope import EventEnvelope
from zml_game_bridge.persistence.event_projector import EventProjector
from zml_game_bridge.persistence.event_writer import EventWriter
from zml_game_bridge.persistence.runs import RunSegmentStore, RunStore
from zml_game_bridge.persistence.schema import ensure_schema
from zml_game_bridge.persistence.sqlite import open_sqlite


@dataclass(frozen=True, slots=True)
class DummyEvent(EventBase):
    x: int = 1


@dataclass(frozen=True, slots=True)
class TransientDummyEvent(EventBase):
    persist: ClassVar[bool] = False

    x: int = 1


class FailingProjector(EventProjector):
    def project(
        self,
        *,
        conn: sqlite3.Connection,
        event: EventBase,
        envelope: EventEnvelope,
    ) -> None:
        _ = (conn, event, envelope)
        raise RuntimeError("projection failed")


def test_event_writer_commits_transaction(tmp_path: Path) -> None:
    db_path = tmp_path / "events.sqlite3"
    conn = open_sqlite(db_path)
    ensure_schema(conn)

    try:
        env = EventWriter(conn).write(DummyEvent(7))
    finally:
        conn.close()

    conn = open_sqlite(db_path)
    try:
        row = conn.execute(
            "SELECT event_type, payload_json FROM events WHERE event_id = ?",
            (env.event_id,),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row["event_type"] == "DummyEvent"
    assert row["payload_json"] == '{"x":7}'


def test_event_writer_stores_event_dt_and_raw_outside_payload(tmp_path: Path) -> None:
    db_path = tmp_path / "events.sqlite3"
    conn = open_sqlite(db_path)
    ensure_schema(conn)
    event_dt = datetime(2026, 1, 10, 12, 37, 50)
    raw = "2026-01-10 12:37:50 [System] [] You received Blue Crystal x (8) Value: 0.1600 PED"

    try:
        env = EventWriter(conn).write(
            MiningItemReceivedEvent(
                event_dt=event_dt,
                item_name="Blue Crystal",
                qty=8,
                value_mpec=Mpec(16_000),
                raw=raw,
            )
        )
    finally:
        conn.close()

    conn = open_sqlite(db_path)
    try:
        row = conn.execute(
            "SELECT event_type, payload_json, event_dt, raw FROM events WHERE event_id = ?",
            (env.event_id,),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row["event_type"] == "MiningItemReceivedEvent"
    assert (
        row["payload_json"]
        == '{"item_name":"Blue Crystal","qty":8,"value_mpec":16000,"extraction_cost_mpec":null,"run_id":null}'
    )
    assert row["event_dt"] == "2026-01-10T12:37:50"
    assert row["raw"] == raw


def test_event_writer_stores_run_segment_context_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "events.sqlite3"
    conn = open_sqlite(db_path)
    ensure_schema(conn)
    event_dt = datetime(2026, 1, 10, 12, 37, 50)

    try:
        run_id = RunStore(conn).create_run(name="Run", notes=None, ts_ms=900)
        RunSegmentStore(conn).create(
            run_id=run_id,
            segment_id="segment-1",
            segment_index=1,
            started_ts_ms=1_000,
            setup_hash="hash-1",
            setup_snapshot={"finder": {"name": "Finder"}},
            ts_ms=1_000,
        )
        env = EventWriter(conn).write(
            MiningClaimDeedReceivedEvent(
                event_dt=event_dt,
                resource_name="Lysterium Stone",
                mining_type="ore",
                deed_item_name="Mineral Resource Deed",
                qty=1,
                value_mpec=Mpec(0),
                raw="deed raw\nclaimed raw",
                run_id=run_id,
                segment_id="segment-1",
            )
        )
    finally:
        conn.close()

    conn = open_sqlite(db_path)
    try:
        row = conn.execute(
            "SELECT run_id, segment_id FROM events WHERE event_id = ?",
            (env.event_id,),
        ).fetchone()
    finally:
        conn.close()

    assert row is not None
    assert row["run_id"] == run_id
    assert row["segment_id"] == "segment-1"


def test_event_writer_rolls_back_event_when_projection_fails(tmp_path: Path) -> None:
    db_path = tmp_path / "events.sqlite3"
    conn = open_sqlite(db_path)
    ensure_schema(conn)

    try:
        try:
            EventWriter(conn, projector=FailingProjector()).write(DummyEvent(7))
        except RuntimeError as exc:
            assert str(exc) == "projection failed"
        else:
            raise AssertionError("Expected projection failure")
    finally:
        conn.close()

    conn = open_sqlite(db_path)
    try:
        count = int(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])
    finally:
        conn.close()

    assert count == 0


def test_event_writer_rejects_transient_events(tmp_path: Path) -> None:
    db_path = tmp_path / "events.sqlite3"
    conn = open_sqlite(db_path)
    ensure_schema(conn)

    try:
        try:
            EventWriter(conn).write(TransientDummyEvent(7))
        except ValueError as exc:
            assert str(exc) == "Refusing to persist transient event: TransientDummyEvent"
        else:
            raise AssertionError("Expected transient event rejection")
    finally:
        conn.close()

    conn = open_sqlite(db_path)
    try:
        count = int(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])
    finally:
        conn.close()

    assert count == 0
