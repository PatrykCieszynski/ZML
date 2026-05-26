from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from zml_game_bridge.domain.mining_events import MiningItemReceivedEvent
from zml_game_bridge.domain.money import Mpec, mpec_to_int
from zml_game_bridge.events.base import EventBase
from zml_game_bridge.events.envelope import EventEnvelope
from zml_game_bridge.persistence.event_projector import EventProjector


@dataclass(frozen=True, slots=True)
class MiningLootItemRow:
    event_id: int
    created_ts_ms: int
    event_dt: datetime | None
    run_id: int | None
    item_name: str
    qty: int
    value_mpec: Mpec
    extraction_cost_mpec: Mpec | None


class MiningLootReader:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def list_all(self, *, run_id: int | None = None) -> list[MiningLootItemRow]:
        where_clause = "" if run_id is None else "WHERE run_id = ?"
        params: tuple[int, ...] = () if run_id is None else (run_id,)
        cur = self._conn.execute(
            f"""
            SELECT *
            FROM mining_loot_items
            {where_clause}
            ORDER BY created_ts_ms DESC, event_id DESC
            """,
            params,
        )
        return [_row_to_loot_item(row) for row in cur.fetchall()]


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


def _row_to_loot_item(row: sqlite3.Row) -> MiningLootItemRow:
    return MiningLootItemRow(
        event_id=int(row["event_id"]),
        created_ts_ms=int(row["created_ts_ms"]),
        event_dt=_optional_datetime(row["event_dt"]),
        run_id=_optional_int(row["run_id"]),
        item_name=str(row["item_name"]),
        qty=int(row["qty"]),
        value_mpec=Mpec(int(row["value_mpec"])),
        extraction_cost_mpec=(
            Mpec(int(row["extraction_cost_mpec"]))
            if row["extraction_cost_mpec"] is not None
            else None
        ),
    )


def _optional_int(value: Any) -> int | None:
    return int(value) if value is not None else None


def _optional_datetime(value: Any) -> datetime | None:
    return datetime.fromisoformat(str(value)) if value is not None else None
