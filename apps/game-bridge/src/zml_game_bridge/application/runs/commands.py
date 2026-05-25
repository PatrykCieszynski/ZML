"""Transitional DB-backed run commands.

Run commands currently enter through the runtime queue and execute on the
single DB writer. Do not copy this RuntimeCommand + DbCommand pattern into new
domains; split pure runtime commands from persistence when run lifecycle moves
to durable domain events.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass

from zml_game_bridge.persistence.run_state import RunState
from zml_game_bridge.persistence.runs import RunRow, RunSegmentStore, RunStore
from zml_game_bridge.runtime.db_commands import DbCommand
from zml_game_bridge.runtime.runtime_commands import RuntimeCommand


class RunCommandError(Exception):
    """Base class for user-facing run command failures."""


class InvalidRunCommandError(RunCommandError):
    pass


class RunNotFoundError(RunCommandError):
    def __init__(self, run_id: int) -> None:
        super().__init__(f"Run not found: {run_id}")
        self.run_id = run_id


class NoActiveRunError(RunCommandError):
    def __init__(self) -> None:
        super().__init__("No active run")


@dataclass(frozen=True, slots=True)
class StartRunCommand(RuntimeCommand[RunRow], DbCommand[RunRow]):
    name: str
    notes: str | None = None

    def execute(self, conn: sqlite3.Connection) -> RunRow:
        name = self.name.strip()
        if not name:
            raise InvalidRunCommandError("Run name must not be empty")

        state = RunState(conn)
        run_id = state.create_run(name=name, notes=self.notes, activate=True)
        row = RunStore(conn).get_run(run_id)
        if row is None:
            raise RuntimeError("Run was not created")
        return row


@dataclass(frozen=True, slots=True)
class StopRunCommand(RuntimeCommand[RunRow], DbCommand[RunRow]):
    run_id: int | None = None

    def execute(self, conn: sqlite3.Connection) -> RunRow:
        store = RunStore(conn)
        state = RunState(conn)

        run_id = self.run_id if self.run_id is not None else state.try_get_active_run_id()
        if run_id is None:
            raise NoActiveRunError()

        row = store.get_run(run_id)
        if row is None:
            raise RunNotFoundError(run_id)

        ts_ms = _now_ms()
        store.set_run_status(run_id, status="stopped", ts_ms=ts_ms)
        RunSegmentStore(conn).end_active_for_run(run_id, ended_ts_ms=ts_ms, ts_ms=ts_ms)
        state.clear_active_run(run_id)
        stopped = store.get_run(run_id)

        if stopped is None:
            raise RuntimeError("Run disappeared while stopping")
        return stopped


@dataclass(frozen=True, slots=True)
class ResumeRunCommand(RuntimeCommand[RunRow], DbCommand[RunRow]):
    run_id: int

    def execute(self, conn: sqlite3.Connection) -> RunRow:
        store = RunStore(conn)
        state = RunState(conn)

        row = store.get_run(self.run_id)
        if row is None:
            raise RunNotFoundError(self.run_id)

        ts_ms = _now_ms()
        active_run_id = state.try_get_active_run_id()
        if active_run_id is not None and active_run_id != self.run_id:
            store.set_run_status(active_run_id, status="stopped", ts_ms=ts_ms)
            RunSegmentStore(conn).end_active_for_run(
                active_run_id,
                ended_ts_ms=ts_ms,
                ts_ms=ts_ms,
            )

        store.set_run_status(self.run_id, status="running", ts_ms=ts_ms)
        state.set_active_run(self.run_id)
        resumed = store.get_run(self.run_id)

        if resumed is None:
            raise RuntimeError("Run disappeared while resuming")
        return resumed


@dataclass(frozen=True, slots=True)
class UpdateRunCommand(RuntimeCommand[RunRow], DbCommand[RunRow]):
    run_id: int
    name: str | None = None
    notes: str | None = None
    notes_set: bool = False

    def execute(self, conn: sqlite3.Connection) -> RunRow:
        store = RunStore(conn)
        row = store.get_run(self.run_id)
        if row is None:
            raise RunNotFoundError(self.run_id)

        if self.name is None and not self.notes_set:
            raise InvalidRunCommandError("Run name or notes is required")

        name = self.name.strip() if self.name is not None else None
        if name is not None and not name:
            raise InvalidRunCommandError("Run name must not be empty")

        notes = self.notes if self.notes_set else row.notes
        store.update_run_meta(self.run_id, name=name, notes=notes, ts_ms=_now_ms())
        updated = store.get_run(self.run_id)

        if updated is None:
            raise RuntimeError("Run disappeared while updating")
        return updated


def _now_ms() -> int:
    return time.time_ns() // 1_000_000
