# zml_game_bridge/app/run_state.py
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Final

ACTIVE_RUN_ID_KEY: Final[str] = "active_run_id"


@dataclass(slots=True)
class RunState:
    """
    Keeps the current "active run" pointer and persists it in app_state.

    Notes:
      - Cache active_run_id in memory (avoid DB reads on each event).
      - All mutating ops should be executed on the single DB-writer thread.
    """

    _conn: sqlite3.Connection
    _active_run_id: int | None = None

    # ---------- lifecycle ----------

    def bootstrap(self) -> int:
        """
        Ensure active run exists:
          - load active_run_id from app_state
          - validate it exists in runs
          - if missing/invalid -> create a new run + persist in app_state
        Returns:
          active_run_id
        """
        raise NotImplementedError

    # ---------- queries ----------

    @property
    def active_run_id(self) -> int:
        """Return cached active_run_id. bootstrap() must be called first."""
        if self._active_run_id is None:
            raise RuntimeError("RunState not bootstrapped")
        return self._active_run_id

    def try_get_active_run_id(self) -> int | None:
        """Return cached id or None (if not bootstrapped)."""
        return self._active_run_id

    # ---------- commands (mutations) ----------

    def create_run(self, *, name: str, notes: str | None = None, activate: bool = True) -> int:
        """
        Insert into runs, set timestamps, default status='active'.
        If activate=True -> also set as active_run_id (cache + app_state).
        """
        raise NotImplementedError

    def set_active_run(self, run_id: int) -> None:
        """
        Validate run exists, then:
          - persist to app_state
          - update in-memory cache
        """
        raise NotImplementedError

    def on_run_deleted(self, run_id: int) -> None:
        """
        Called after deletion (or before, depending on your delete flow).
        If the deleted run was active -> create a new run and activate it.
        """
        raise NotImplementedError

    # ---------- low-level helpers (still part of run_state, not repo) ----------

    def _load_active_run_id_from_db(self) -> int | None:
        """Read app_state['active_run_id'] and parse it safely."""
        raise NotImplementedError

    def _persist_active_run_id(self, run_id: int) -> None:
        """INSERT OR REPLACE into app_state."""
        raise NotImplementedError

    def _run_exists(self, run_id: int) -> bool:
        """SELECT 1 FROM runs WHERE run_id=?."""
        raise NotImplementedError
