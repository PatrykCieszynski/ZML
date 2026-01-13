from __future__ import annotations

from zml_game_bridge.events.in_memory_persisted_event_bus import InMemoryPersistedEventBus
from zml_game_bridge.events.envelope import EventEnvelope


def _env(i: int = 1) -> EventEnvelope:
    return EventEnvelope(
        event_id=i,
        created_ts_ms=123,
        event_dt=None,
        event_type="TestEvent",
        payload_json='{"x":1}',
    )


def test_bus_publish_delivers_to_subscriber() -> None:
    bus = InMemoryPersistedEventBus()
    out: list[EventEnvelope] = []

    sub = bus.subscribe(lambda e: out.append(e))
    bus.publish(_env(1))

    assert out == [_env(1)]
    sub.close()


def test_bus_unsubscribe_stops_delivery() -> None:
    bus = InMemoryPersistedEventBus()
    out: list[EventEnvelope] = []

    sub = bus.subscribe(lambda e: out.append(e))
    sub.close()

    bus.publish(_env(1))
    assert out == []


def test_bus_handler_exception_does_not_break_others() -> None:
    bus = InMemoryPersistedEventBus()
    out: list[EventEnvelope] = []

    def bad(_e: EventEnvelope) -> None:
        raise RuntimeError("boom")

    bus.subscribe(bad)
    bus.subscribe(lambda e: out.append(e))

    bus.publish(_env(1))

    assert out == [_env(1)]
