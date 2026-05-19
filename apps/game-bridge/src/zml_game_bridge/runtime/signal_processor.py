from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol

from zml_game_bridge.events.base import EventBase


class SignalProcessor(Protocol):
    def process(self, signal: EventBase) -> Iterable[EventBase]:
        """Return durable domain events derived from a received input signal."""
        ...


class NoOpSignalProcessor:
    def process(self, _signal: EventBase) -> tuple[EventBase, ...]:
        return ()


class CompositeSignalProcessor:
    def __init__(self, processors: Sequence[SignalProcessor]) -> None:
        self._processors = tuple(processors)

    def process(self, signal: EventBase) -> list[EventBase]:
        derived: list[EventBase] = []
        for processor in self._processors:
            derived.extend(processor.process(signal))
        return derived
