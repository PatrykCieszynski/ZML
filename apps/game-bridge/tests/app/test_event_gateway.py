from __future__ import annotations

from dataclasses import dataclass

from zml_game_bridge.app.event_channel import EventChannel


@dataclass(frozen=True, slots=True)
class DummyEvent:
    x: int


def test_gateway_emit_then_take_returns_same_event() -> None:
    gw = EventChannel(maxsize=10)
    ev = DummyEvent(x=123)

    gw.emit(ev)  # type: ignore[arg-type]
    got = gw.take(timeout_s=0.1)

    assert got == ev


def test_gateway_take_timeout_returns_none() -> None:
    gw = EventChannel(maxsize=10)

    got = gw.take(timeout_s=0.01)
    assert got is None
