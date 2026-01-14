from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

import zml_game_bridge.app.event_persister as event_persister_mod
from zml_game_bridge.app.event_channel import EventChannel
from zml_game_bridge.events.in_memory_persisted_event_bus import InMemoryPersistedEventBus
from zml_game_bridge.events.envelope import EventEnvelope


# --- Dummy domain event (doesn't matter what fields) ---
@dataclass(frozen=True, slots=True)
class DummyEvent:
    x: int = 1


# --- Fake EventStore injected via monkeypatch ---
class FakeEventStore:
    last_instance: "FakeEventStore | None" = None

    def __init__(self, _db_path: Any) -> None:
        self.open_calls = 0
        self.close_calls = 0
        self.append_calls: list[Any] = []
        self._next_id = 1
        FakeEventStore.last_instance = self

    def open(self) -> None:
        self.open_calls += 1

    def close(self) -> None:
        self.close_calls += 1

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


def test_db_writer_persists_and_publishes(monkeypatch) -> None:
    # Patch EventStore used by EventPersister
    monkeypatch.setattr(event_persister_mod, "EventStore", FakeEventStore)

    bus = InMemoryPersistedEventBus()
    gw = EventChannel(maxsize=10)
    writer = event_persister_mod.EventPersister(db_path=":memory:", gateway=gw, bus=bus)  # db_path ignored by fake

    out: list[EventEnvelope] = []
    got = threading.Event()

    sub = bus.subscribe(lambda env: (out.append(env), got.set()))

    stop = threading.Event()
    t = threading.Thread(target=writer.run, kwargs={"stop_event": stop}, daemon=True)
    t.start()

    # Emit one event
    gw.emit(DummyEvent(42))  # type: ignore[arg-type]

    assert got.wait(timeout=1.0), "EventPersister didn't publish anything"
    stop.set()
    t.join(timeout=1.0)

    # Assertions
    assert len(out) == 1
    assert out[0].event_type == "DummyEvent"

    inst = FakeEventStore.last_instance
    assert inst is not None
    assert inst.open_calls == 1
    assert inst.close_calls == 1
    assert len(inst.append_calls) == 1
    assert isinstance(inst.append_calls[0], DummyEvent)

    sub.close()


def test_db_writer_no_event_no_publish(monkeypatch) -> None:
    monkeypatch.setattr(event_persister_mod, "EventStore", FakeEventStore)

    bus = InMemoryPersistedEventBus()
    gw = EventChannel(maxsize=10)
    writer = event_persister_mod.EventPersister(db_path=":memory:", gateway=gw, bus=bus)

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
    assert inst.open_calls == 1
    assert inst.close_calls == 1
    assert inst.append_calls == []

    sub.close()
