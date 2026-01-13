from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from .envelope import EventEnvelope

EventHandler = Callable[[EventEnvelope], None]

@dataclass(slots=True)
class Subscription:
    """A handle that allows unsubscribing from an PersistedEventBus."""
    unsubscribe: Callable[[], None]

    def close(self) -> None:
        self.unsubscribe()


class PersistedEventBus(Protocol):
    """Dispatches persisted EventEnvelope objects to subscribers."""

    def publish(self, envelope: EventEnvelope) -> None:
        ...

    def subscribe(self, handler: EventHandler) -> Subscription:
        ...
