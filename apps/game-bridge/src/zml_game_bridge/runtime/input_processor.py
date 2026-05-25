from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol

from zml_game_bridge.events.base import EventBase
from zml_game_bridge.runtime.runtime_commands import (
    RuntimeCommand,
    RuntimeCommandResult,
    UnsupportedRuntimeCommandError,
)


class InputProcessor(Protocol):
    def process(self, signal: EventBase) -> Iterable[EventBase]:
        """Return durable domain events derived from a received input signal."""
        ...

    def process_command[T](self, command: RuntimeCommand[T]) -> RuntimeCommandResult[T]:
        """Execute a runtime command and return its response plus optional events."""
        ...


class NoOpInputProcessor:
    def process(self, _signal: EventBase) -> tuple[EventBase, ...]:
        return ()

    def process_command[T](self, command: RuntimeCommand[T]) -> RuntimeCommandResult[T]:
        raise UnsupportedRuntimeCommandError(type(command).__name__)


class CompositeInputProcessor:
    def __init__(self, processors: Sequence[InputProcessor]) -> None:
        self._processors = tuple(processors)

    def process(self, signal: EventBase) -> list[EventBase]:
        derived: list[EventBase] = []
        for processor in self._processors:
            derived.extend(processor.process(signal))
        return derived

    def process_command[T](self, command: RuntimeCommand[T]) -> RuntimeCommandResult[T]:
        last_error: UnsupportedRuntimeCommandError | None = None
        for processor in self._processors:
            try:
                return processor.process_command(command)
            except UnsupportedRuntimeCommandError as exc:
                last_error = exc
        raise last_error or UnsupportedRuntimeCommandError(type(command).__name__)
