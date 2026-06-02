from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, cast

from zml_game_bridge.domain.mining_events import MiningItemReceivedEvent
from zml_game_bridge.domain.money import Mpec, mpec_to_int
from zml_game_bridge.events.base import EventBase
from zml_game_bridge.events.envelope import EventEnvelope
from zml_game_bridge.persistence.event_projector import EventProjector

RECENT_LOOT_LIMIT = 25
MiningLootTotalScope = Literal["run", "segment"]


@dataclass(frozen=True, slots=True)
class MiningLootItemRow:
    event_id: int
    created_ts_ms: int
    event_dt: datetime | None
    run_id: int | None
    segment_id: str | None
    item_name: str
    qty: int
    value_mpec: Mpec
    extraction_cost_mpec: Mpec | None


@dataclass(frozen=True, slots=True)
class MiningLootTotalRow:
    scope: MiningLootTotalScope
    run_id: int
    segment_id: str | None
    item_name: str
    qty: int
    value_mpec: Mpec
    extraction_cost_mpec: Mpec
    event_count: int
    first_seen_ts_ms: int
    last_seen_ts_ms: int


@dataclass(frozen=True, slots=True)
class MiningLootWriteResult:
    recent_item: MiningLootItemRow
    run_total: MiningLootTotalRow | None
    segment_total: MiningLootTotalRow | None


@dataclass(frozen=True, slots=True)
class RecordMiningLootItemCommand:
    event_dt: datetime
    item_name: str
    qty: int
    value_mpec: Mpec
    raw: str
    extraction_cost_mpec: Mpec | None
    run_id: int | None
    segment_id: str | None
    created_ts_ms: int | None = None

    def execute(self, conn: sqlite3.Connection) -> MiningLootWriteResult:
        writer = MiningLootWriter(conn)
        return writer.record_item(
            event_dt=self.event_dt,
            item_name=self.item_name,
            qty=self.qty,
            value_mpec=self.value_mpec,
            raw=self.raw,
            extraction_cost_mpec=self.extraction_cost_mpec,
            run_id=self.run_id,
            segment_id=self.segment_id,
            created_ts_ms=self.created_ts_ms,
        )


class MiningLootReader:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def list_recent(
        self,
        *,
        run_id: int | None = None,
        limit: int = RECENT_LOOT_LIMIT,
    ) -> list[MiningLootItemRow]:
        where_clause = "" if run_id is None else "WHERE run_id = ?"
        params: tuple[int, ...] = () if run_id is None else (run_id,)
        cur = self._conn.execute(
            f"""
            SELECT loot_id AS event_id, created_ts_ms, event_dt, run_id, segment_id,
                   item_name, qty, value_mpec, extraction_cost_mpec
            FROM mining_loot_recent
            {where_clause}
            ORDER BY created_ts_ms DESC, loot_id DESC
            LIMIT ?
            """,
            (*params, limit),
        )
        return [_row_to_loot_item(row) for row in cur.fetchall()]

    def list_all(self, *, run_id: int | None = None) -> list[MiningLootItemRow]:
        return self.list_recent(run_id=run_id)

    def list_run_totals(self, *, run_id: int | None = None) -> list[MiningLootTotalRow]:
        where_clause = "" if run_id is None else "WHERE run_id = ?"
        params: tuple[int, ...] = () if run_id is None else (run_id,)
        cur = self._conn.execute(
            f"""
            SELECT 'run' AS scope, run_id, NULL AS segment_id, item_name, qty, value_mpec,
                   extraction_cost_mpec, event_count, first_seen_ts_ms, last_seen_ts_ms
            FROM run_item_totals
            {where_clause}
            ORDER BY value_mpec DESC, item_name ASC
            """,
            params,
        )
        return [_row_to_loot_total(row) for row in cur.fetchall()]

    def list_segment_totals(self, *, segment_id: str | None = None) -> list[MiningLootTotalRow]:
        where_clause = "" if segment_id is None else "WHERE segment_id = ?"
        params: tuple[str, ...] = () if segment_id is None else (segment_id,)
        cur = self._conn.execute(
            f"""
            SELECT 'segment' AS scope, run_id, segment_id, item_name, qty, value_mpec,
                   extraction_cost_mpec, event_count, first_seen_ts_ms, last_seen_ts_ms
            FROM segment_item_totals
            {where_clause}
            ORDER BY value_mpec DESC, item_name ASC
            """,
            params,
        )
        return [_row_to_loot_total(row) for row in cur.fetchall()]


class MiningLootWriter:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def record_item(
        self,
        *,
        event_dt: datetime,
        item_name: str,
        qty: int,
        value_mpec: Mpec,
        raw: str,
        extraction_cost_mpec: Mpec | None,
        run_id: int | None,
        segment_id: str | None,
        created_ts_ms: int | None = None,
    ) -> MiningLootWriteResult:
        created_ts_ms = created_ts_ms if created_ts_ms is not None else time.time_ns() // 1_000_000
        value_mpec_int = mpec_to_int(value_mpec)
        extraction_cost_int = (
            mpec_to_int(extraction_cost_mpec) if extraction_cost_mpec is not None else None
        )
        self._conn.execute(
            """
            INSERT INTO mining_loot_recent (
                created_ts_ms, event_dt, run_id, segment_id, item_name, qty,
                value_mpec, extraction_cost_mpec, raw
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                created_ts_ms,
                event_dt.isoformat(),
                run_id,
                segment_id,
                item_name,
                qty,
                value_mpec_int,
                extraction_cost_int,
                raw,
            ),
        )
        loot_id = _last_insert_row_id(self._conn)
        run_total = self._record_run_total(
            run_id=run_id,
            item_name=item_name,
            qty=qty,
            value_mpec=value_mpec_int,
            extraction_cost_mpec=extraction_cost_int or 0,
            seen_ts_ms=created_ts_ms,
        )
        segment_total = self._record_segment_total(
            run_id=run_id,
            segment_id=segment_id,
            item_name=item_name,
            qty=qty,
            value_mpec=value_mpec_int,
            extraction_cost_mpec=extraction_cost_int or 0,
            seen_ts_ms=created_ts_ms,
        )
        _delete_old_recent_items(self._conn, run_id=run_id, limit=RECENT_LOOT_LIMIT)
        recent_item = _select_recent_item(self._conn, loot_id=loot_id)
        return MiningLootWriteResult(
            recent_item=recent_item,
            run_total=run_total,
            segment_total=segment_total,
        )

    def _record_run_total(
        self,
        *,
        run_id: int | None,
        item_name: str,
        qty: int,
        value_mpec: int,
        extraction_cost_mpec: int,
        seen_ts_ms: int,
    ) -> MiningLootTotalRow | None:
        if run_id is None:
            return None
        self._conn.execute(
            """
            INSERT INTO run_item_totals (
                run_id, item_name, qty, value_mpec, extraction_cost_mpec,
                event_count, first_seen_ts_ms, last_seen_ts_ms
            )
            VALUES (?, ?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(run_id, item_name) DO UPDATE SET
                qty = qty + excluded.qty,
                value_mpec = value_mpec + excluded.value_mpec,
                extraction_cost_mpec = extraction_cost_mpec + excluded.extraction_cost_mpec,
                event_count = event_count + 1,
                first_seen_ts_ms = MIN(first_seen_ts_ms, excluded.first_seen_ts_ms),
                last_seen_ts_ms = MAX(last_seen_ts_ms, excluded.last_seen_ts_ms)
            """,
            (
                run_id,
                item_name,
                qty,
                value_mpec,
                extraction_cost_mpec,
                seen_ts_ms,
                seen_ts_ms,
            ),
        )
        return _select_run_total(self._conn, run_id=run_id, item_name=item_name)

    def _record_segment_total(
        self,
        *,
        run_id: int | None,
        segment_id: str | None,
        item_name: str,
        qty: int,
        value_mpec: int,
        extraction_cost_mpec: int,
        seen_ts_ms: int,
    ) -> MiningLootTotalRow | None:
        if run_id is None or segment_id is None:
            return None
        self._conn.execute(
            """
            INSERT INTO segment_item_totals (
                segment_id, run_id, item_name, qty, value_mpec, extraction_cost_mpec,
                event_count, first_seen_ts_ms, last_seen_ts_ms
            )
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(segment_id, item_name) DO UPDATE SET
                qty = qty + excluded.qty,
                value_mpec = value_mpec + excluded.value_mpec,
                extraction_cost_mpec = extraction_cost_mpec + excluded.extraction_cost_mpec,
                event_count = event_count + 1,
                first_seen_ts_ms = MIN(first_seen_ts_ms, excluded.first_seen_ts_ms),
                last_seen_ts_ms = MAX(last_seen_ts_ms, excluded.last_seen_ts_ms)
            """,
            (
                segment_id,
                run_id,
                item_name,
                qty,
                value_mpec,
                extraction_cost_mpec,
                seen_ts_ms,
                seen_ts_ms,
            ),
        )
        return _select_segment_total(self._conn, segment_id=segment_id, item_name=item_name)


class MiningLootProjector(EventProjector):
    def project(
        self,
        *,
        conn: sqlite3.Connection,
        event: EventBase,
        envelope: EventEnvelope,
    ) -> None:
        if isinstance(event, MiningItemReceivedEvent):
            _MiningLootProjectionWriter(conn).upsert_item(event=event, envelope=envelope)


class _MiningLootProjectionWriter:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def upsert_item(
        self,
        *,
        event: MiningItemReceivedEvent,
        envelope: EventEnvelope,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO mining_loot_items (
                event_id, created_ts_ms, event_dt, run_id,
                item_name, qty, value_mpec, extraction_cost_mpec, raw
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id) DO UPDATE SET
                created_ts_ms = excluded.created_ts_ms,
                event_dt = excluded.event_dt,
                run_id = excluded.run_id,
                item_name = excluded.item_name,
                qty = excluded.qty,
                value_mpec = excluded.value_mpec,
                extraction_cost_mpec = excluded.extraction_cost_mpec,
                raw = excluded.raw
            """,
            (
                envelope.event_id,
                envelope.created_ts_ms,
                event.event_dt.isoformat(),
                event.run_id,
                event.item_name,
                event.qty,
                mpec_to_int(event.value_mpec),
                (
                    mpec_to_int(event.extraction_cost_mpec)
                    if event.extraction_cost_mpec is not None
                    else None
                ),
                event.raw,
            ),
        )


def _select_recent_item(conn: sqlite3.Connection, *, loot_id: int) -> MiningLootItemRow:
    row = conn.execute(
        """
        SELECT loot_id AS event_id, created_ts_ms, event_dt, run_id, segment_id,
               item_name, qty, value_mpec, extraction_cost_mpec
        FROM mining_loot_recent
        WHERE loot_id = ?
        """,
        (loot_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Recorded loot item was not found: {loot_id}")
    return _row_to_loot_item(row)


def _select_run_total(
    conn: sqlite3.Connection,
    *,
    run_id: int,
    item_name: str,
) -> MiningLootTotalRow:
    row = conn.execute(
        """
        SELECT 'run' AS scope, run_id, NULL AS segment_id, item_name, qty, value_mpec,
               extraction_cost_mpec, event_count, first_seen_ts_ms, last_seen_ts_ms
        FROM run_item_totals
        WHERE run_id = ? AND item_name = ?
        """,
        (run_id, item_name),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Run loot total was not found: run_id={run_id} item={item_name!r}")
    return _row_to_loot_total(row)


def _select_segment_total(
    conn: sqlite3.Connection,
    *,
    segment_id: str,
    item_name: str,
) -> MiningLootTotalRow:
    row = conn.execute(
        """
        SELECT 'segment' AS scope, run_id, segment_id, item_name, qty, value_mpec,
               extraction_cost_mpec, event_count, first_seen_ts_ms, last_seen_ts_ms
        FROM segment_item_totals
        WHERE segment_id = ? AND item_name = ?
        """,
        (segment_id, item_name),
    ).fetchone()
    if row is None:
        raise RuntimeError(
            f"Segment loot total was not found: segment_id={segment_id} item={item_name!r}"
        )
    return _row_to_loot_total(row)


def _delete_old_recent_items(conn: sqlite3.Connection, *, run_id: int | None, limit: int) -> None:
    if run_id is None:
        conn.execute(
            """
            DELETE FROM mining_loot_recent
            WHERE run_id IS NULL
              AND loot_id NOT IN (
                  SELECT loot_id
                  FROM mining_loot_recent
                  WHERE run_id IS NULL
                  ORDER BY created_ts_ms DESC, loot_id DESC
                  LIMIT ?
              )
            """,
            (limit,),
        )
        return
    conn.execute(
        """
        DELETE FROM mining_loot_recent
        WHERE run_id = ?
          AND loot_id NOT IN (
              SELECT loot_id
              FROM mining_loot_recent
              WHERE run_id = ?
              ORDER BY created_ts_ms DESC, loot_id DESC
              LIMIT ?
          )
        """,
        (run_id, run_id, limit),
    )


def _last_insert_row_id(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT last_insert_rowid()").fetchone()
    if row is None:
        raise RuntimeError("Failed to retrieve last inserted loot row id")
    return int(row[0])


def _row_to_loot_item(row: sqlite3.Row) -> MiningLootItemRow:
    return MiningLootItemRow(
        event_id=int(row["event_id"]),
        created_ts_ms=int(row["created_ts_ms"]),
        event_dt=_optional_datetime(row["event_dt"]),
        run_id=_optional_int(row["run_id"]),
        segment_id=_optional_str(row["segment_id"]),
        item_name=str(row["item_name"]),
        qty=int(row["qty"]),
        value_mpec=Mpec(int(row["value_mpec"])),
        extraction_cost_mpec=(
            Mpec(int(row["extraction_cost_mpec"]))
            if row["extraction_cost_mpec"] is not None
            else None
        ),
    )


def _row_to_loot_total(row: sqlite3.Row) -> MiningLootTotalRow:
    return MiningLootTotalRow(
        scope=cast(MiningLootTotalScope, str(row["scope"])),
        run_id=int(row["run_id"]),
        segment_id=_optional_str(row["segment_id"]),
        item_name=str(row["item_name"]),
        qty=int(row["qty"]),
        value_mpec=Mpec(int(row["value_mpec"])),
        extraction_cost_mpec=Mpec(int(row["extraction_cost_mpec"])),
        event_count=int(row["event_count"]),
        first_seen_ts_ms=int(row["first_seen_ts_ms"]),
        last_seen_ts_ms=int(row["last_seen_ts_ms"]),
    )


def _optional_int(value: Any) -> int | None:
    return int(value) if value is not None else None


def _optional_str(value: Any) -> str | None:
    return str(value) if value is not None else None


def _optional_datetime(value: Any) -> datetime | None:
    return datetime.fromisoformat(str(value)) if value is not None else None
