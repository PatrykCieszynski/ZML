from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, cast

from zml_game_bridge.domain.mining_events import RunSegmentEndedEvent, RunSegmentStartedEvent
from zml_game_bridge.domain.money import Mpec
from zml_game_bridge.events.base import EventBase
from zml_game_bridge.events.envelope import EventEnvelope
from zml_game_bridge.persistence.event_projector import EventProjector


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
    segment_id: str
    run_id: int
    segment_index: int
    status: str
    started_ts_ms: int
    ended_ts_ms: int | None
    setup_hash: str
    setup_snapshot: Mapping[str, Any]
    notes: str | None
    created_ts_ms: int
    updated_ts_ms: int


class RunStore:
    """
    SQLite access for runs.
    - No active-run selection logic here; that belongs to persistence.run_state.
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

    def list_runs(
        self,
        *,
        status: str | None = None,
        include_deleted: bool = False,
        limit: int = 200,
    ) -> list[RunRow]:
        """List runs, optionally filtered by status."""
        if status is None:
            where_clause = "" if include_deleted else "WHERE status != 'deleted'"
            cur = self._conn.execute(
                f"""
                SELECT run_id, name, notes, status, created_ts_ms, updated_ts_ms
                FROM runs
                {where_clause}
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

    def mark_run_deleted(self, run_id: int, *, ts_ms: int) -> None:
        """Soft-delete a run; dependent rows remain available for recovery/history."""
        self.set_run_status(run_id, status="deleted", ts_ms=ts_ms)

    def calc_total_cost_mpec(self, run_id: int) -> Mpec:
        """SUM(total_cost_mpec) over projected mining drops for the run."""
        cur = self._conn.execute(
            """
            SELECT COALESCE(SUM(total_cost_mpec), 0) AS total
            FROM mining_drops
            WHERE run_id = ?
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
        segment_id: str,
        segment_index: int,
        started_ts_ms: int,
        setup_hash: str,
        setup_snapshot: Mapping[str, Any],
        notes: str | None = None,
        ts_ms: int,
    ) -> str:
        """Insert segment, return segment_id."""
        self._conn.execute(
            """
            INSERT INTO run_segments (
                segment_id, run_id, segment_index, status,
                started_ts_ms, ended_ts_ms, setup_hash, setup_snapshot_json,
                notes, created_ts_ms, updated_ts_ms
            )
            VALUES (?, ?, ?, 'active', ?, NULL, ?, ?, ?, ?, ?)
            ON CONFLICT(segment_id) DO UPDATE SET
                run_id = excluded.run_id,
                segment_index = excluded.segment_index,
                status = excluded.status,
                started_ts_ms = excluded.started_ts_ms,
                ended_ts_ms = excluded.ended_ts_ms,
                setup_hash = excluded.setup_hash,
                setup_snapshot_json = excluded.setup_snapshot_json,
                notes = excluded.notes,
                updated_ts_ms = excluded.updated_ts_ms
            """,
            (
                segment_id,
                run_id,
                segment_index,
                started_ts_ms,
                setup_hash,
                _json_dump(setup_snapshot),
                notes,
                ts_ms,
                ts_ms,
            ),
        )
        return segment_id

    def get(self, segment_id: str) -> RunSegmentRow | None:
        """Return segment or None."""
        cur = self._conn.execute(
            """
            SELECT segment_id, run_id, segment_index, status, started_ts_ms, ended_ts_ms,
                   setup_hash, setup_snapshot_json, notes, created_ts_ms, updated_ts_ms
            FROM run_segments
            WHERE segment_id = ?
            """,
            (segment_id,),
        )
        row = cur.fetchone()
        return _row_to_segment(row) if row is not None else None

    def list_for_run(self, run_id: int, *, include_inactive: bool = True) -> list[RunSegmentRow]:
        """List segments ordered by sort_key,segment_id."""
        if include_inactive:
            cur = self._conn.execute(
                """
                SELECT segment_id, run_id, segment_index, status, started_ts_ms, ended_ts_ms,
                       setup_hash, setup_snapshot_json, notes, created_ts_ms, updated_ts_ms
                FROM run_segments
                WHERE run_id = ?
                ORDER BY segment_index ASC, started_ts_ms ASC
                """,
                (run_id,),
            )
        else:
            cur = self._conn.execute(
                """
                SELECT segment_id, run_id, segment_index, status, started_ts_ms, ended_ts_ms,
                       setup_hash, setup_snapshot_json, notes, created_ts_ms, updated_ts_ms
                FROM run_segments
                WHERE run_id = ? AND status = 'active'
                ORDER BY segment_index ASC, started_ts_ms ASC
                """,
                (run_id,),
            )
        return [_row_to_segment(row) for row in cur.fetchall()]

    def update(
        self,
        segment_id: str,
        *,
        status: str | None = None,
        ended_ts_ms: int | None = None,
        notes: str | None = None,
        ts_ms: int,
    ) -> None:
        """Patch update + updated_ts_ms."""
        self._conn.execute(
            """
            UPDATE run_segments
            SET status = COALESCE(?, status),
                ended_ts_ms = COALESCE(?, ended_ts_ms),
                notes = COALESCE(?, notes),
                updated_ts_ms = ?
            WHERE segment_id = ?
            """,
            (status, ended_ts_ms, notes, ts_ms, segment_id),
        )

    def delete(self, segment_id: str) -> None:
        """Delete segment."""
        self._conn.execute("DELETE FROM run_segments WHERE segment_id = ?", (segment_id,))

    def reorder(self, run_id: int, *, ordered_segment_ids: list[str], ts_ms: int) -> None:
        """
        Apply ordering by updating segment_index.
        Must validate all ids belong to run_id.
        """
        known = {segment.segment_id for segment in self.list_for_run(run_id)}
        if set(ordered_segment_ids) != known:
            raise ValueError("ordered_segment_ids must contain exactly all segment ids for the run")
        for index, segment_id in enumerate(ordered_segment_ids, start=1):
            self._conn.execute(
                """
                UPDATE run_segments
                SET segment_index = ?, updated_ts_ms = ?
                WHERE run_id = ? AND segment_id = ?
                """,
                (index, ts_ms, run_id, segment_id),
            )

    def calc_total_cost_mpec(self, run_id: int) -> Mpec:
        """SUM(total_cost_mpec) for projected drops in this run."""
        return RunStore(self._conn).calc_total_cost_mpec(run_id)

    def set_active(self, segment_id: str, *, is_active: bool, ts_ms: int) -> None:
        """Compatibility helper: active maps to status='active', inactive to status='ended'."""
        self.update(
            segment_id,
            status="active" if is_active else "ended",
            ts_ms=ts_ms,
        )

    def end_active_for_run(self, run_id: int, *, ended_ts_ms: int, ts_ms: int) -> int:
        cur = self._conn.execute(
            """
            UPDATE run_segments
            SET status = 'ended',
                ended_ts_ms = COALESCE(ended_ts_ms, ?),
                updated_ts_ms = ?
            WHERE run_id = ? AND status = 'active'
            """,
            (ended_ts_ms, ts_ms, run_id),
        )
        return int(cur.rowcount)

    def clone_to_run(
        self,
        segment_id: str,
        *,
        target_run_id: int,
        ts_ms: int,
        overrides: Mapping[str, Any] | None = None,
    ) -> str:
        """
        Duplicate segment into another run (or same run).
        Overrides is a shallow dict for fields like segment_id/segment_index/notes/setup_snapshot.
        """
        source = self.get(segment_id)
        if source is None:
            raise ValueError(f"Segment not found: {segment_id}")
        item = dict(overrides or {})
        cloned_id = str(item.get("segment_id", f"{segment_id}-copy"))
        setup_snapshot = item.get("setup_snapshot", source.setup_snapshot)
        if not isinstance(setup_snapshot, Mapping):
            raise ValueError("setup_snapshot override must be a mapping")
        notes = item.get("notes", source.notes)
        if notes is not None and not isinstance(notes, str):
            raise ValueError("notes override must be a string or None")
        return self.create(
            run_id=target_run_id,
            segment_id=cloned_id,
            segment_index=int(item.get("segment_index", source.segment_index)),
            started_ts_ms=int(item.get("started_ts_ms", source.started_ts_ms)),
            setup_hash=str(item.get("setup_hash", source.setup_hash)),
            setup_snapshot=cast(Mapping[str, Any], setup_snapshot),
            notes=notes,
            ts_ms=ts_ms,
        )


class RunSegmentProjector(EventProjector):
    def project(
        self,
        *,
        conn: sqlite3.Connection,
        event: EventBase,
        envelope: EventEnvelope,
    ) -> None:
        store = RunSegmentStore(conn)
        if isinstance(event, RunSegmentStartedEvent):
            store.create(
                run_id=event.run_id,
                segment_id=event.segment_id,
                segment_index=event.segment_index,
                started_ts_ms=event.started_ts_ms,
                setup_hash=event.setup_hash,
                setup_snapshot=event.setup_snapshot,
                ts_ms=envelope.created_ts_ms,
            )
        elif isinstance(event, RunSegmentEndedEvent):
            store.update(
                event.segment_id,
                status="ended",
                ended_ts_ms=event.ended_ts_ms,
                ts_ms=envelope.created_ts_ms,
            )


def _row_to_run(row: sqlite3.Row) -> RunRow:
    return RunRow(
        run_id=int(row["run_id"]),
        name=str(row["name"]),
        notes=row["notes"],
        status=str(row["status"]),
        created_ts_ms=int(row["created_ts_ms"]),
        updated_ts_ms=int(row["updated_ts_ms"]),
    )


def _row_to_segment(row: sqlite3.Row) -> RunSegmentRow:
    return RunSegmentRow(
        segment_id=str(row["segment_id"]),
        run_id=int(row["run_id"]),
        segment_index=int(row["segment_index"]),
        status=str(row["status"]),
        started_ts_ms=int(row["started_ts_ms"]),
        ended_ts_ms=int(row["ended_ts_ms"]) if row["ended_ts_ms"] is not None else None,
        setup_hash=str(row["setup_hash"]),
        setup_snapshot=_json_load_mapping(str(row["setup_snapshot_json"])),
        notes=row["notes"],
        created_ts_ms=int(row["created_ts_ms"]),
        updated_ts_ms=int(row["updated_ts_ms"]),
    )


def _json_dump(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _json_load_mapping(value: str) -> Mapping[str, Any]:
    raw = json.loads(value)
    if not isinstance(raw, dict):
        return {}
    return cast(dict[str, Any], raw)
