from __future__ import annotations

from queue import Empty, Queue

from zml_game_bridge.events.base import EventBase


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


class SignalChannel(RuntimeChannel[EventBase]):
    """
    Queue for input observations waiting for runtime coordination.

    Most values here should be SignalBase instances. Current chat input still
    emits legacy EventBase classes and should be migrated to signals when the
    mining chat flow is implemented.
    """


class EventChannel(RuntimeChannel[EventBase]):
    """Queue for durable domain events waiting for the DB writer."""
