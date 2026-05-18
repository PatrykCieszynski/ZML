from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from zml_game_bridge.events.base import EventBase
from zml_game_bridge.persistence.event_writer import EventWriter
from zml_game_bridge.persistence.schema import ensure_schema
from zml_game_bridge.persistence.sqlite import open_sqlite


@dataclass(frozen=True, slots=True)
class DummyEvent(EventBase):
    x: int = 1


class FailingProjector:
    def project(self, **_kwargs: object) -> None:
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
