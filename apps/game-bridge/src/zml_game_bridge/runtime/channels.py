from __future__ import annotations

import threading
from queue import Empty, Queue
from typing import Any

from zml_game_bridge.events.base import EventBase
from zml_game_bridge.runtime.event_requests import EventWriteRequest
from zml_game_bridge.runtime.runtime_commands import RuntimeCommandRequest


class ChannelClosed:
    """Sentinel returned by take() after the channel has been closed and drained."""


CHANNEL_CLOSED = ChannelClosed()


class ChannelClosedError(RuntimeError):
    pass


class RuntimeChannel[T]:
    """Thread-safe queue for values crossing runtime worker boundaries."""

    _q: Queue[T | ChannelClosed]

    def __init__(self, *, maxsize: int = 10_000) -> None:
        self._q = Queue(maxsize=maxsize)
        self._closed = False
        self._lock = threading.Lock()

    def emit(self, item: T) -> None:
        """Blocking by default (backpressure)."""
        with self._lock:
            if self._closed:
                raise ChannelClosedError(f"{type(self).__name__} is closed")
            # Hold the lock while putting so close() cannot enqueue the sentinel
            # ahead of an item that was already accepted by a producer.
            self._q.put(item)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._q.put(CHANNEL_CLOSED)

    def take(self, *, timeout_s: float) -> T | ChannelClosed | None:
        """Consumer side. Returns None on timeout or CHANNEL_CLOSED after close()."""
        try:
            return self._q.get(timeout=timeout_s)
        except Empty:
            return None

    def is_closed(self) -> bool:
        with self._lock:
            return self._closed

    def size(self) -> int:
        return self._q.qsize()


class RuntimeInputChannel(RuntimeChannel[EventBase | RuntimeCommandRequest[Any]]):
    """Queue for input observations and API commands waiting for runtime coordination."""


class EventChannel(RuntimeChannel[EventBase | EventWriteRequest]):
    """Queue for durable domain events waiting for the DB writer."""
