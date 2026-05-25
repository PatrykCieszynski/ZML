from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Generic, TypeVar, cast

from zml_game_bridge.events.base import EventBase

T = TypeVar("T")


class UnsupportedRuntimeCommandError(Exception):
    def __init__(self, command_type: str) -> None:
        super().__init__(f"Unsupported runtime command: {command_type}")
        self.command_type = command_type


class RuntimeCommand(Generic[T]):
    """Marker base for commands that enter the runtime input queue."""

    __slots__ = ()


@dataclass(frozen=True, slots=True)
class RuntimeCommandResult(Generic[T]):
    value: T
    events: tuple[EventBase, ...] = ()


@dataclass(slots=True)
class RuntimeCommandRequest(Generic[T]):
    command: RuntimeCommand[T]
    _done: threading.Event = field(default_factory=threading.Event, init=False)
    _result: T | None = field(default=None, init=False)
    _error: BaseException | None = field(default=None, init=False)

    def set_result(self, result: T) -> None:
        self._result = result
        self._done.set()

    def set_exception(self, error: BaseException) -> None:
        self._error = error
        self._done.set()

    def result(self, *, timeout_s: float) -> T:
        if not self._done.wait(timeout=timeout_s):
            raise TimeoutError(
                f"Timed out waiting for runtime command: {type(self.command).__name__}"
            )
        if self._error is not None:
            raise self._error
        return cast(T, self._result)
