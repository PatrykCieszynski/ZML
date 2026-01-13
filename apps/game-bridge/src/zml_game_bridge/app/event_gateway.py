from __future__ import annotations

from queue import Queue, Empty

from zml_game_bridge.events.base import EventBase


class EventGateway:
    _q: Queue[EventBase]

    def __init__(self, *, maxsize: int = 10_000) -> None:
        self._q = Queue(maxsize=maxsize)

    def emit(self, event: EventBase) -> None:
        """Blocking by default (backpressure)."""
        # TODO: Backpressure policy:
        # - block indefinitely (current)
        # - block with timeout + drop
        # - non-blocking drop (put_nowait)
        self._q.put(event)

    def take(self, *, timeout_s: float) -> EventBase | None:
        """Consumer side. Returns None on timeout."""
        try:
            return self._q.get(timeout=timeout_s)
        except Empty:
            return None

    def size(self) -> int:
        return self._q.qsize()
