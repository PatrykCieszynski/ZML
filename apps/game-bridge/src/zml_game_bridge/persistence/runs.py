from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from zml_game_bridge.domain.money import Mpec


@dataclass(frozen=True, slots=True)
class RunRow:
    run_id: int
    name: str
    notes: str | None
    status: str
    created_ts_ms: int
    updated_ts_ms: int


@dataclass(frozen=True, slots=True)
class RunSegmentRow:
    segment_id: int
    run_id: int
    kind: str
    label: str
    qty: int
    unit_cost_mpec: Mpec
    total_cost_mpec: Mpec
    is_active: bool
    meta: Mapping[str, Any]
    sort_key: int
    created_ts_ms: int
    updated_ts_ms: int


class RunStore:
    """
    SQLite access for runs.
    - No active-run selection logic here; that belongs to runs.state.
    - Keep writes low-volume and wrapped by callers when multiple mutations belong together.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create_run(
        self,
        *,
        name: str,
        notes: str | None,
        ts_ms: int,
        status: str = "running",
    ) -> int:
        """Insert into runs and return run_id."""
        cur = self._conn.execute(
            """
            INSERT INTO runs (name, notes, created_ts_ms, updated_ts_ms, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, notes, ts_ms, ts_ms, status),
        )
        rowid = cur.lastrowid
        if rowid is None:
            raise RuntimeError("Failed to retrieve lastrowid after run insert")
        return int(rowid)

    def get_run(self, run_id: int) -> RunRow | None:
        """Return a run or None."""
        cur = self._conn.execute(
            """
            SELECT run_id, name, notes, status, created_ts_ms, updated_ts_ms
            FROM runs
            WHERE run_id = ?
            """,
            (run_id,),
        )
        row = cur.fetchone()
        return _row_to_run(row) if row is not None else None

    def list_runs(self, *, status: str | None = None, limit: int = 200) -> list[RunRow]:
        """List runs, optionally filtered by status."""
        if status is None:
            cur = self._conn.execute(
                """
                SELECT run_id, name, notes, status, created_ts_ms, updated_ts_ms
                FROM runs
                ORDER BY updated_ts_ms DESC, run_id DESC
                LIMIT ?
                """,
                (limit,),
            )
        else:
            cur = self._conn.execute(
                """
                SELECT run_id, name, notes, status, created_ts_ms, updated_ts_ms
                FROM runs
                WHERE status = ?
                ORDER BY updated_ts_ms DESC, run_id DESC
                LIMIT ?
                """,
                (status, limit),
            )
        return [_row_to_run(row) for row in cur.fetchall()]

    def update_run_meta(
        self,
        run_id: int,
        *,
        name: str | None,
        notes: str | None,
        ts_ms: int,
    ) -> None:
        """Update run fields + updated_ts_ms."""
        self._conn.execute(
            """
            UPDATE runs
            SET name = COALESCE(?, name),
                notes = ?,
                updated_ts_ms = ?
            WHERE run_id = ?
            """,
            (name, notes, ts_ms, run_id),
        )

    def set_run_status(self, run_id: int, *, status: str, ts_ms: int) -> None:
        """Update status + updated_ts_ms."""
        self._conn.execute(
            """
            UPDATE runs
            SET status = ?, updated_ts_ms = ?
            WHERE run_id = ?
            """,
            (status, ts_ms, run_id),
        )

    def delete_run(self, run_id: int) -> None:
        """Delete a run and let foreign-key cascades handle dependent rows."""
        self._conn.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))

    def calc_total_cost_mpec(self, run_id: int) -> Mpec:
        """SUM(total_cost_mpec) over active segments."""
        cur = self._conn.execute(
            """
            SELECT COALESCE(SUM(total_cost_mpec), 0) AS total
            FROM run_segments
            WHERE run_id = ? AND is_active = 1
            """,
            (run_id,),
        )
        return Mpec(int(cur.fetchone()["total"]))

    def assign_events_to_run(self, *, run_id: int, event_ids: Iterable[int]) -> int:
        """
        Bulk UPDATE events SET run_id=? WHERE event_id IN (...).
        Returns number of rows updated.
        """
        ids = list(event_ids)
        if not ids:
            return 0

        placeholders = ",".join("?" for _ in ids)
        cur = self._conn.execute(
            f"UPDATE events SET run_id = ? WHERE event_id IN ({placeholders})",
            (run_id, *ids),
        )
        return int(cur.rowcount)

    def clear_events_run(self, *, event_ids: Iterable[int]) -> int:
        """Bulk UPDATE events SET run_id=NULL."""
        ids = list(event_ids)
        if not ids:
            return 0

        placeholders = ",".join("?" for _ in ids)
        cur = self._conn.execute(
            f"UPDATE events SET run_id = NULL WHERE event_id IN ({placeholders})",
            ids,
        )
        return int(cur.rowcount)


class RunSegmentStore:
    """
    SQLite access for run_segments table.
    Assumption: used from a single-writer DB thread.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(
        self,
        *,
        run_id: int,
        kind: str,
        label: str,
        qty: int,
        unit_cost_mpec: Mpec,
        is_active: bool,
        meta: Mapping[str, Any],
        sort_key: int,
        ts_ms: int,
    ) -> int:
        """Insert segment, return segment_id."""
        raise NotImplementedError

    def get(self, segment_id: int) -> RunSegmentRow | None:
        """Return segment or None."""
        raise NotImplementedError

    def list_for_run(self, run_id: int, *, include_inactive: bool = True) -> list[RunSegmentRow]:
        """List segments ordered by sort_key,segment_id."""
        raise NotImplementedError

    def update(
        self,
        segment_id: int,
        *,
        kind: str | None = None,
        label: str | None = None,
        qty: int | None = None,
        unit_cost_mpec: Mpec | None = None,
        is_active: bool | None = None,
        meta: Mapping[str, Any] | None = None,
        sort_key: int | None = None,
        ts_ms: int,
    ) -> None:
        """Patch update + updated_ts_ms."""
        raise NotImplementedError

    def delete(self, segment_id: int) -> None:
        """Delete segment."""
        raise NotImplementedError

    def reorder(self, run_id: int, *, ordered_segment_ids: list[int], ts_ms: int) -> None:
        """
        Apply ordering by updating sort_key.
        Must validate all ids belong to run_id.
        """
        raise NotImplementedError

    def calc_total_cost_mpec(self, run_id: int) -> Mpec:
        """SUM(total_cost_mpec) for active segments."""
        raise NotImplementedError

    def set_active(self, segment_id: int, *, is_active: bool, ts_ms: int) -> None:
        """Toggle segment active flag."""
        raise NotImplementedError

    def clone_to_run(
        self,
        segment_id: int,
        *,
        target_run_id: int,
        ts_ms: int,
        overrides: Mapping[str, Any] | None = None,
    ) -> int:
        """
        Duplicate segment into another run (or same run).
        Overrides is a shallow dict for fields like label/qty/unit_cost/meta/sort_key.
        """
        raise NotImplementedError


def _row_to_run(row: sqlite3.Row) -> RunRow:
    return RunRow(
        run_id=int(row["run_id"]),
        name=str(row["name"]),
        notes=row["notes"],
        status=str(row["status"]),
        created_ts_ms=int(row["created_ts_ms"]),
        updated_ts_ms=int(row["updated_ts_ms"]),
    )
