from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from typing import Final

from zml_game_bridge.persistence.runs import RunStore

ACTIVE_RUN_ID_KEY: Final[str] = "active_run_id"


@dataclass(slots=True)
class RunState:
    """
    Keeps the current active run pointer and persists it in app_state.

    The active pointer is intentionally separate from RunStore: RunStore manages
    rows, while RunState owns the app-level selection.
    """

    _conn: sqlite3.Connection
    _active_run_id: int | None = None

    def bootstrap(self) -> int:
        """
        Ensure active run exists and return its id.

        This is useful for flows that require an active container. UI commands
        can still clear the pointer when a run is explicitly stopped.
        """
        loaded = self._load_active_run_id_from_db()
        if loaded is not None and self._run_exists(loaded):
            self._active_run_id = loaded
            return loaded

        run_id = self.create_run(name="Mining run", activate=True)
        return run_id

    @property
    def active_run_id(self) -> int:
        """Return cached active_run_id. bootstrap() must be called first."""
        if self._active_run_id is None:
            raise RuntimeError("RunState not bootstrapped")
        return self._active_run_id

    def try_get_active_run_id(self) -> int | None:
        """Return cached id or load it lazily from DB."""
        if self._active_run_id is None:
            loaded = self._load_active_run_id_from_db()
            if loaded is not None and self._run_exists(loaded):
                self._active_run_id = loaded
        return self._active_run_id

    def create_run(self, *, name: str, notes: str | None = None, activate: bool = True) -> int:
        """
        Insert into runs, set timestamps, default status='running'.
        If activate=True -> also set as active_run_id.
        """
        ts_ms = _now_ms()
        run_id = RunStore(self._conn).create_run(
            name=name,
            notes=notes,
            ts_ms=ts_ms,
            status="running",
        )
        if activate:
            self._persist_active_run_id(run_id)
            self._active_run_id = run_id
        return run_id

    def set_active_run(self, run_id: int) -> None:
        """
        Validate run exists, then persist and cache active_run_id.
        """
        if not self._run_exists(run_id):
            raise ValueError(f"Run does not exist: {run_id}")
        self._persist_active_run_id(run_id)
        self._active_run_id = run_id

    def clear_active_run(self, run_id: int | None = None) -> None:
        """
        Clear active pointer.

        If run_id is provided, clear only when that run is currently active.
        """
        active = self.try_get_active_run_id()
        if run_id is not None and active != run_id:
            return

        self._conn.execute("DELETE FROM app_state WHERE key = ?", (ACTIVE_RUN_ID_KEY,))
        self._active_run_id = None

    def on_run_deleted(self, run_id: int) -> None:
        """
        Called after deletion. If the deleted run was active, clear the pointer.
        """
        self.clear_active_run(run_id)

    def _load_active_run_id_from_db(self) -> int | None:
        """Read app_state['active_run_id'] and parse it safely."""
        cur = self._conn.execute(
            "SELECT value FROM app_state WHERE key = ?",
            (ACTIVE_RUN_ID_KEY,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        try:
            return int(row["value"])
        except (TypeError, ValueError):
            return None

    def _persist_active_run_id(self, run_id: int) -> None:
        """INSERT OR REPLACE into app_state."""
        self._conn.execute(
            """
            INSERT OR REPLACE INTO app_state(key, value)
            VALUES (?, ?)
            """,
            (ACTIVE_RUN_ID_KEY, str(run_id)),
        )

    def _run_exists(self, run_id: int) -> bool:
        """SELECT 1 FROM runs WHERE run_id=?."""
        cur = self._conn.execute("SELECT 1 FROM runs WHERE run_id = ?", (run_id,))
        return cur.fetchone() is not None


def _now_ms() -> int:
    return time.time_ns() // 1_000_000
