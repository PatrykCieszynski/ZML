from __future__ import annotations

from dataclasses import dataclass

from zml_game_bridge.runtime.channels import EventChannel


@dataclass(frozen=True, slots=True)
class DummyEvent:
    x: int


def test_event_channel_emit_then_take_returns_same_event() -> None:
    channel = EventChannel(maxsize=10)
    ev = DummyEvent(x=123)

    channel.emit(ev)  # type: ignore[arg-type]
    got = channel.take(timeout_s=0.1)

    assert got == ev


def test_event_channel_take_timeout_returns_none() -> None:
    channel = EventChannel(maxsize=10)

    got = channel.take(timeout_s=0.01)
    assert got is None
