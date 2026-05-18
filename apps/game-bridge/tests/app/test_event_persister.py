from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import zml_game_bridge.app.db_writer_worker as db_writer_worker_mod
from zml_game_bridge.app.event_channel import EventChannel
from zml_game_bridge.events.base import EventBase
from zml_game_bridge.events.envelope import EventEnvelope
from zml_game_bridge.events.in_memory_persisted_event_bus import InMemoryPersistedEventBus
from zml_game_bridge.storage.db_schema import ensure_schema
from zml_game_bridge.storage.event_store import EventStore
from zml_game_bridge.storage.sqlite import open_sqlite


# --- Dummy domain event (doesn't matter what fields) ---
@dataclass(frozen=True, slots=True)
class DummyEvent(EventBase):
    x: int = 1


# --- Fake EventStore injected via monkeypatch ---
class FakeEventStore:
    last_instance: FakeEventStore | None = None

    def __init__(self, _conn: Any) -> None:
        self.append_calls: list[Any] = []
        self._next_id = 1
        FakeEventStore.last_instance = self

    def append(self, event: Any) -> EventEnvelope:
        self.append_calls.append(event)
        eid = self._next_id
        self._next_id += 1
        return EventEnvelope(
            event_id=eid,
            created_ts_ms=123,
            event_dt=None,
            event_type=type(event).__name__,
            payload_json='{"ok":true}',
        )


def test_db_writer_persists_and_publishes(monkeypatch, tmp_path: Path) -> None:
    # Patch EventStore used by DbWriterWorker
    monkeypatch.setattr(db_writer_worker_mod, "EventStore", FakeEventStore)

    bus = InMemoryPersistedEventBus()
    gw = EventChannel(maxsize=10)
    writer = db_writer_worker_mod.DbWriterWorker(
        db_path=tmp_path / "events.sqlite3",
        pending_events=gw,
        persisted_events=bus,
    )

    out: list[EventEnvelope] = []
    got = threading.Event()

    sub = bus.subscribe(lambda env: (out.append(env), got.set()))

    stop = threading.Event()
    t = threading.Thread(target=writer.run, kwargs={"stop_event": stop}, daemon=True)
    t.start()

    # Emit one event
    gw.emit(DummyEvent(42))

    assert got.wait(timeout=1.0), "DbWriterWorker didn't publish anything"
    stop.set()
    t.join(timeout=1.0)

    # Assertions
    assert len(out) == 1
    assert out[0].event_type == "DummyEvent"

    inst = FakeEventStore.last_instance
    assert inst is not None
    assert len(inst.append_calls) == 1
    assert isinstance(inst.append_calls[0], DummyEvent)

    sub.close()


def test_db_writer_no_event_no_publish(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(db_writer_worker_mod, "EventStore", FakeEventStore)

    bus = InMemoryPersistedEventBus()
    gw = EventChannel(maxsize=10)
    writer = db_writer_worker_mod.DbWriterWorker(
        db_path=tmp_path / "events.sqlite3",
        pending_events=gw,
        persisted_events=bus,
    )

    out: list[EventEnvelope] = []
    sub = bus.subscribe(lambda env: out.append(env))

    stop = threading.Event()
    t = threading.Thread(target=writer.run, kwargs={"stop_event": stop}, daemon=True)
    t.start()

    # Don't emit anything; let it spin a moment
    time.sleep(0.2)

    stop.set()
    t.join(timeout=1.0)

    assert out == []
    inst = FakeEventStore.last_instance
    assert inst is not None
    assert inst.append_calls == []

    sub.close()


class FailingProjector:
    def project(self, **_kwargs: object) -> None:
        raise RuntimeError("projection failed")


def test_db_writer_persist_event_commits_transaction(tmp_path: Path) -> None:
    db_path = tmp_path / "events.sqlite3"
    writer = db_writer_worker_mod.DbWriterWorker(
        db_path=db_path,
        pending_events=EventChannel(maxsize=10),
        persisted_events=InMemoryPersistedEventBus(),
    )

    writer.open()
    assert writer.conn is not None
    ensure_schema(writer.conn)

    try:
        env = writer._persist_event(EventStore(writer.conn), DummyEvent(7))
    finally:
        writer.close()

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


def test_db_writer_rolls_back_event_when_projection_fails(tmp_path: Path) -> None:
    db_path = tmp_path / "events.sqlite3"
    bus = InMemoryPersistedEventBus()
    gw = EventChannel(maxsize=10)
    writer = db_writer_worker_mod.DbWriterWorker(
        db_path=db_path,
        pending_events=gw,
        persisted_events=bus,
        projector=FailingProjector(),
    )

    out: list[EventEnvelope] = []
    sub = bus.subscribe(lambda env: out.append(env))

    writer.open()
    assert writer.conn is not None
    ensure_schema(writer.conn)

    try:
        try:
            writer._persist_event(EventStore(writer.conn), DummyEvent(7))
        except RuntimeError as exc:
            assert str(exc) == "projection failed"
        else:
            raise AssertionError("Expected projection failure")
    finally:
        writer.close()
        sub.close()

    conn = open_sqlite(db_path)
    try:
        count = int(conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])
    finally:
        conn.close()

    assert count == 0
    assert out == []
