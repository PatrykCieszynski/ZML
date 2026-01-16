# zml_game_bridge/storage/run_store.py
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Iterable

from zml_game_bridge.common.types import Mpec


@dataclass(frozen=True, slots=True)
class RunRow:
    run_id: int
    name: str
    notes: str | None
    status: str
    created_ts_ms: int
    updated_ts_ms: int


class RunStore:
    """
    SQLite access for runs + segments.
    - No "active run" logic here (that's RunState).
    - Assumed to be called from the DB-writer thread (single-writer).
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # -------------------------
    # Runs
    # -------------------------

    def create_run(self, *, name: str, notes: str | None, ts_ms: int) -> int:
        """Insert into runs and return run_id."""
        raise NotImplementedError

    def get_run(self, run_id: int) -> RunRow | None:
        """Return a run or None."""
        raise NotImplementedError

    def list_runs(self, *, status: str | None = None, limit: int = 200) -> list[RunRow]:
        """List runs (optionally filtered by status)."""
        raise NotImplementedError

    def update_run_meta(self, run_id: int, *, name: str | None, notes: str | None, ts_ms: int) -> None:
        """Update run fields + updated_ts_ms."""
        raise NotImplementedError

    def set_run_status(self, run_id: int, *, status: str, ts_ms: int) -> None:
        """Update status + updated_ts_ms."""
        raise NotImplementedError

    def delete_run(self, run_id: int) -> None:
        """
        Delete run.
        Expected DB behavior:
          - segments removed via ON DELETE CASCADE
          - events.run_id removed via ON DELETE CASCADE (or you may prefer SET NULL)
        """
        raise NotImplementedError

    # -------------------------
    # Derived totals (cheap aggregation)
    # -------------------------

    def calc_total_cost_mpec(self, run_id: int) -> Mpec:
        """SUM(total_cost_mpec) over active segments."""
        raise NotImplementedError

    # -------------------------
    # Optional: event assignment to runs
    # -------------------------

    def assign_events_to_run(self, *, run_id: int, event_ids: Iterable[int]) -> int:
        """
        Bulk UPDATE events SET run_id=? WHERE event_id IN (...)
        Returns number of rows updated.
        """
        raise NotImplementedError

    def clear_events_run(self, *, event_ids: Iterable[int]) -> int:
        """Bulk UPDATE events SET run_id=NULL ..."""
        raise NotImplementedError
