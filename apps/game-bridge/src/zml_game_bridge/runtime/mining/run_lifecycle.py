from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar, cast

from zml_game_bridge.persistence.runs import RunRow
from zml_game_bridge.runtime.db_commands import DbCommand
from zml_game_bridge.runtime.run_commands import (
    ResumeRunCommand,
    StartRunCommand,
    StopRunCommand,
    UpdateRunCommand,
)
from zml_game_bridge.runtime.runtime_commands import (
    RuntimeCommand,
    RuntimeCommandResult,
    UnsupportedRuntimeCommandError,
)

T = TypeVar("T")


class RunLifecycle:
    """
    Runtime-facing run command handler.

    Today run commands still mutate the run projection directly through the DB
    writer command queue. Keeping this behind MiningCoordinator gives us one
    input path now, and a small replacement point if runs become event-sourced.
    """

    def __init__(self, *, db_command_executor: Callable[[DbCommand[Any]], Any]) -> None:
        self._db_command_executor = db_command_executor

    def process_command(self, command: RuntimeCommand[T]) -> RuntimeCommandResult[T]:
        if isinstance(
            command,
            StartRunCommand | StopRunCommand | ResumeRunCommand | UpdateRunCommand,
        ):
            result = self._db_command_executor(cast(DbCommand[RunRow], command))
            return cast(RuntimeCommandResult[T], RuntimeCommandResult(value=result))
        raise UnsupportedRuntimeCommandError(type(command).__name__)
