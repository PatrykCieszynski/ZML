from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import zml_game_bridge.runtime.db_writer as db_writer_worker_mod
from zml_game_bridge.events.base import EventBase
from zml_game_bridge.events.envelope import EventEnvelope
from zml_game_bridge.events.in_memory_persisted_event_bus import InMemoryPersistedEventBus
from zml_game_bridge.runtime.channels import EventChannel


@dataclass(frozen=True, slots=True)
class DummyEvent(EventBase):
    x: int = 1


class FakeEventWriter:
    last_instance: FakeEventWriter | None = None

    def __init__(self, _conn: Any, *, projector: object | None = None) -> None:
        self.write_calls: list[Any] = []
        self._next_id = 1
        self.projector = projector
        FakeEventWriter.last_instance = self

    def write(self, event: EventBase) -> EventEnvelope:
        self.write_calls.append(event)
        event_id = self._next_id
        self._next_id += 1
        return EventEnvelope(
            event_id=event_id,
            created_ts_ms=123,
            event_dt=None,
            event_type=type(event).__name__,
            payload_json='{"ok":true}',
        )


def test_db_writer_persists_and_publishes(monkeypatch, tmp_path: Path) -> None:
    FakeEventWriter.last_instance = None
    monkeypatch.setattr(db_writer_worker_mod, "EventWriter", FakeEventWriter)

    bus = InMemoryPersistedEventBus()
    channel = EventChannel(maxsize=10)
    writer = db_writer_worker_mod.DbWriterWorker(
        db_path=tmp_path / "events.sqlite3",
        pending_events=channel,
        persisted_events=bus,
    )

    out: list[EventEnvelope] = []
    got = threading.Event()
    sub = bus.subscribe(lambda env: (out.append(env), got.set()))

    stop = threading.Event()
    thread = threading.Thread(target=writer.run, kwargs={"stop_event": stop}, daemon=True)
    thread.start()

    channel.emit(DummyEvent(42))

    assert got.wait(timeout=1.0), "DbWriterWorker didn't publish anything"
    stop.set()
    thread.join(timeout=1.0)

    assert len(out) == 1
    assert out[0].event_type == "DummyEvent"

    inst = FakeEventWriter.last_instance
    assert inst is not None
    assert len(inst.write_calls) == 1
    assert isinstance(inst.write_calls[0], DummyEvent)

    sub.close()


def test_db_writer_no_event_no_publish(monkeypatch, tmp_path: Path) -> None:
    FakeEventWriter.last_instance = None
    monkeypatch.setattr(db_writer_worker_mod, "EventWriter", FakeEventWriter)

    bus = InMemoryPersistedEventBus()
    channel = EventChannel(maxsize=10)
    writer = db_writer_worker_mod.DbWriterWorker(
        db_path=tmp_path / "events.sqlite3",
        pending_events=channel,
        persisted_events=bus,
    )

    out: list[EventEnvelope] = []
    sub = bus.subscribe(lambda env: out.append(env))

    stop = threading.Event()
    thread = threading.Thread(target=writer.run, kwargs={"stop_event": stop}, daemon=True)
    thread.start()

    time.sleep(0.2)

    stop.set()
    thread.join(timeout=1.0)

    assert out == []
    inst = FakeEventWriter.last_instance
    assert inst is not None
    assert inst.write_calls == []

    sub.close()
