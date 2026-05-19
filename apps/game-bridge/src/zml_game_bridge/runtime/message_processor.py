from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol

from zml_game_bridge.events.base import EventBase


class RuntimeMessageProcessor(Protocol):
    def process(self, message: EventBase) -> Iterable[EventBase]:
        """Return derived runtime messages for a received event or signal."""
        ...


class NoOpRuntimeMessageProcessor:
    def process(self, _message: EventBase) -> tuple[EventBase, ...]:
        return ()


class CompositeRuntimeMessageProcessor:
    def __init__(self, processors: Sequence[RuntimeMessageProcessor]) -> None:
        self._processors = tuple(processors)

    def process(self, message: EventBase) -> list[EventBase]:
        derived: list[EventBase] = []
        for processor in self._processors:
            derived.extend(processor.process(message))
        return derived
