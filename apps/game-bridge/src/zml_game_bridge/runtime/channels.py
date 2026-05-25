from __future__ import annotations

from queue import Empty, Queue
from typing import Any
from warnings import deprecated

from zml_game_bridge.events.base import EventBase
from zml_game_bridge.runtime.event_requests import EventWriteRequest
from zml_game_bridge.runtime.runtime_commands import RuntimeCommandRequest


class RuntimeChannel[T]:
    """Thread-safe queue for values crossing runtime worker boundaries."""

    _q: Queue[T]

    def __init__(self, *, maxsize: int = 10_000) -> None:
        self._q = Queue(maxsize=maxsize)

    def emit(self, item: T) -> None:
        """Blocking by default (backpressure)."""
        # TODO: Backpressure policy:
        # - block indefinitely (current)
        # - block with timeout + drop
        # - non-blocking drop (put_nowait)
        self._q.put(item)

    def take(self, *, timeout_s: float) -> T | None:
        """Consumer side. Returns None on timeout."""
        try:
            return self._q.get(timeout=timeout_s)
        except Empty:
            return None

    def size(self) -> int:
        return self._q.qsize()


class RuntimeInputChannel(RuntimeChannel[EventBase | RuntimeCommandRequest[Any]]):
    """Queue for input observations and API commands waiting for runtime coordination."""


@deprecated("Use RuntimeInputChannel instead.")
class SignalChannel(RuntimeInputChannel):
    """Compatibility alias for input adapters that still speak in signals."""


class EventChannel(RuntimeChannel[EventBase | EventWriteRequest]):
    """Queue for durable domain events waiting for the DB writer."""
