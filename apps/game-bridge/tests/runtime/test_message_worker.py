from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import ClassVar

from zml_game_bridge.events.base import EventBase
from zml_game_bridge.events.envelope import EventEnvelope
from zml_game_bridge.events.in_memory_persisted_event_bus import InMemoryPersistedEventBus
from zml_game_bridge.runtime.event_queue import EventChannel
from zml_game_bridge.runtime.message_worker import RuntimeMessageWorker


@dataclass(frozen=True, slots=True)
class DurableDummyEvent(EventBase):
    x: int


@dataclass(frozen=True, slots=True)
class TransientDummySignal(EventBase):
    persist: ClassVar[bool] = False

    x: int


class FakeMessageProcessor:
    def process(self, message: EventBase) -> list[EventBase]:
        if isinstance(message, TransientDummySignal):
            return [DurableDummyEvent(message.x + 1)]
        return []


def test_message_worker_routes_transient_signal_to_live_bus_and_derived_event_to_writer_queue() -> None:
    incoming = EventChannel(maxsize=10)
    pending_events = EventChannel(maxsize=10)
    live_events = InMemoryPersistedEventBus()
    worker = RuntimeMessageWorker(
        pending_messages=incoming,
        pending_events=pending_events,
        live_events=live_events,
        message_processor=FakeMessageProcessor(),
    )

    out: list[EventEnvelope] = []
    got = threading.Event()
    sub = live_events.subscribe(lambda env: (out.append(env), got.set()))

    stop = threading.Event()
    thread = threading.Thread(target=worker.run, kwargs={"stop_event": stop}, daemon=True)
    thread.start()

    incoming.emit(TransientDummySignal(41))

    assert got.wait(timeout=1.0), "RuntimeMessageWorker didn't publish transient signal"
    derived = pending_events.take(timeout_s=1.0)

    stop.set()
    thread.join(timeout=1.0)

    assert len(out) == 1
    assert out[0].event_id == -1
    assert out[0].event_type == "TransientDummySignal"
    assert out[0].payload_json == '{"x":41}'
    assert derived == DurableDummyEvent(42)

    sub.close()


def test_message_worker_routes_durable_event_to_writer_queue() -> None:
    incoming = EventChannel(maxsize=10)
    pending_events = EventChannel(maxsize=10)
    live_events = InMemoryPersistedEventBus()
    worker = RuntimeMessageWorker(
        pending_messages=incoming,
        pending_events=pending_events,
        live_events=live_events,
    )

    stop = threading.Event()
    thread = threading.Thread(target=worker.run, kwargs={"stop_event": stop}, daemon=True)
    thread.start()

    incoming.emit(DurableDummyEvent(7))
    event = pending_events.take(timeout_s=1.0)

    stop.set()
    thread.join(timeout=1.0)

    assert event == DurableDummyEvent(7)


def test_message_worker_assigns_unique_negative_ids_to_transient_signals() -> None:
    incoming = EventChannel(maxsize=10)
    pending_events = EventChannel(maxsize=10)
    live_events = InMemoryPersistedEventBus()
    worker = RuntimeMessageWorker(
        pending_messages=incoming,
        pending_events=pending_events,
        live_events=live_events,
    )

    out: list[EventEnvelope] = []
    got = threading.Event()

    def collect(env: EventEnvelope) -> None:
        out.append(env)
        if len(out) == 2:
            got.set()

    sub = live_events.subscribe(collect)

    stop = threading.Event()
    thread = threading.Thread(target=worker.run, kwargs={"stop_event": stop}, daemon=True)
    thread.start()

    incoming.emit(TransientDummySignal(1))
    incoming.emit(TransientDummySignal(2))

    assert got.wait(timeout=1.0), "RuntimeMessageWorker didn't publish both signals"
    stop.set()
    thread.join(timeout=1.0)

    assert [env.event_id for env in out] == [-1, -2]

    sub.close()
