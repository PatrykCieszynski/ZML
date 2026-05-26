from __future__ import annotations

import threading
from dataclasses import dataclass, field

from zml_game_bridge.events.base import EventBase
from zml_game_bridge.events.envelope import EventEnvelope


@dataclass(slots=True)
class EventWriteRequest:
    event: EventBase
    _done: threading.Event = field(default_factory=threading.Event, init=False)
    _envelope: EventEnvelope | None = field(default=None, init=False)
    _error: BaseException | None = field(default=None, init=False)

    def set_result(self, envelope: EventEnvelope) -> None:
        self._envelope = envelope
        self._done.set()

    def set_exception(self, error: BaseException) -> None:
        self._error = error
        self._done.set()

    def result(self, *, timeout_s: float) -> EventEnvelope:
        if not self._done.wait(timeout=timeout_s):
            raise TimeoutError(f"Timed out waiting for event write: {type(self.event).__name__}")
        if self._error is not None:
            raise self._error
        if self._envelope is None:
            raise RuntimeError("Event write finished without envelope")
        return self._envelope
