from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

from zml_game_bridge.runtime.channels import RuntimeChannel


class DbCommand[T_co](Protocol):
    """A synchronous DB write/read unit executed by DbWriterWorker."""

    def execute(self, conn: sqlite3.Connection) -> T_co: ...


@dataclass(slots=True)
class DbCommandRequest[T]:
    command: DbCommand[T]
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
            raise TimeoutError(f"Timed out waiting for DB command: {type(self.command).__name__}")
        if self._error is not None:
            raise self._error
        return cast(T, self._result)


class DbCommandChannel(RuntimeChannel[DbCommandRequest[Any]]):
    """Thread-safe queue for API/runtime commands that must use the DB writer."""

    def execute[T](self, command: DbCommand[T], *, timeout_s: float = 5.0) -> T:
        request = DbCommandRequest(command)
        self.emit(request)
        return request.result(timeout_s=timeout_s)
