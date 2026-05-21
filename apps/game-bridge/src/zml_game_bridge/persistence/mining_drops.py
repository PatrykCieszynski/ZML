from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Literal, cast

from zml_game_bridge.domain.mining_events import (
    MiningDropEvent,
    MiningHitHintEvent,
    MiningNoResourcesEvent,
)
from zml_game_bridge.domain.money import Mpec, mpec_to_int
from zml_game_bridge.domain.position import WorldPos
from zml_game_bridge.events.base import EventBase
from zml_game_bridge.events.envelope import EventEnvelope
from zml_game_bridge.persistence.event_projector import EventProjector

MiningDropResult = Literal["pending", "hit", "no_resources"]


@dataclass(frozen=True, slots=True)
class MiningDropRow:
    drop_id: str
    drop_event_id: int
    observed_ts_ms: int
    position: WorldPos | None
    drop_radius_m: float
    modes_mask: int | None
    probes_per_drop: int | None
    ammo_per_drop: int | None
    ammo_cost_mpec: Mpec
    probes_cost_mpec: Mpec
    finder_decay_mpec: Mpec
    finder_enhancer_decay_mpec: Mpec
    amp_decay_mpec: Mpec
    total_cost_mpec: Mpec
    result: MiningDropResult
    result_event_id: int | None
    result_observed_ts_ms: int | None
    hit_id: str | None
    hit_event_id: int | None
    resource_name: str | None
    size_label: str | None
    size_index: int | None
    expected_expires_ts_ms: int | None
    range_m: float | None
    depth_m: float | None


class MiningDropReader:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def list_since(self, *, since_ts_ms: int) -> list[MiningDropRow]:
        cur = self._conn.execute(
            """
            SELECT *
            FROM mining_drops
            WHERE observed_ts_ms >= ?
            ORDER BY observed_ts_ms DESC, drop_event_id DESC
            """,
            (since_ts_ms,),
        )
        return [_row_to_mining_drop(row) for row in cur.fetchall()]

    def get(self, drop_id: str) -> MiningDropRow | None:
        cur = self._conn.execute(
            """
            SELECT *
            FROM mining_drops
            WHERE drop_id = ?
            """,
            (drop_id,),
        )
        row = cur.fetchone()
        return _row_to_mining_drop(row) if row is not None else None


class MiningDropProjector(EventProjector):
    def project(
        self,
        *,
        conn: sqlite3.Connection,
        event: EventBase,
        envelope: EventEnvelope,
    ) -> None:
        writer = _MiningDropProjectionWriter(conn)
        if isinstance(event, MiningDropEvent):
            writer.upsert_drop(event=event, event_id=envelope.event_id)
        elif isinstance(event, MiningHitHintEvent):
            writer.mark_hit(event=event, event_id=envelope.event_id)
        elif isinstance(event, MiningNoResourcesEvent):
            writer.mark_no_resources(event=event, event_id=envelope.event_id)


class _MiningDropProjectionWriter:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def upsert_drop(self, *, event: MiningDropEvent, event_id: int) -> None:
        position = event.position
        self._conn.execute(
            """
            INSERT INTO mining_drops (
                drop_id, drop_event_id, observed_ts_ms,
                planet_name, x, y, z, drop_radius_m,
                modes_mask, probes_per_drop, ammo_per_drop,
                ammo_cost_mpec, probes_cost_mpec, finder_decay_mpec,
                finder_enhancer_decay_mpec, amp_decay_mpec, total_cost_mpec,
                result
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
            ON CONFLICT(drop_id) DO UPDATE SET
                drop_event_id = excluded.drop_event_id,
                observed_ts_ms = excluded.observed_ts_ms,
                planet_name = excluded.planet_name,
                x = excluded.x,
                y = excluded.y,
                z = excluded.z,
                drop_radius_m = excluded.drop_radius_m,
                modes_mask = excluded.modes_mask,
                probes_per_drop = excluded.probes_per_drop,
                ammo_per_drop = excluded.ammo_per_drop,
                ammo_cost_mpec = excluded.ammo_cost_mpec,
                probes_cost_mpec = excluded.probes_cost_mpec,
                finder_decay_mpec = excluded.finder_decay_mpec,
                finder_enhancer_decay_mpec = excluded.finder_enhancer_decay_mpec,
                amp_decay_mpec = excluded.amp_decay_mpec,
                total_cost_mpec = excluded.total_cost_mpec
            """,
            (
                event.drop_id,
                event_id,
                event.observed_ts_ms,
                position.planet_name if position is not None else None,
                position.x if position is not None else None,
                position.y if position is not None else None,
                position.z if position is not None else None,
                event.drop_radius_m if event.drop_radius_m is not None else 55.0,
                event.modes_mask,
                event.probes_per_drop,
                event.ammo_per_drop,
                mpec_to_int(event.cost.ammo.cost_mpec),
                mpec_to_int(event.cost.probes.cost_mpec),
                mpec_to_int(event.cost.finder_decay_mpec),
                mpec_to_int(event.cost.finder_enhancer_decay_mpec),
                mpec_to_int(event.cost.amp_decay_mpec),
                mpec_to_int(event.cost.total_mpec),
            ),
        )

    def mark_hit(self, *, event: MiningHitHintEvent, event_id: int) -> None:
        if event.drop_id is None:
            return
        # TODO: This read model stores only the single finder hint for MVP.
        # Real claims/deeds should be projected into a separate claim/deed model,
        # because one multi-mode drop can create more than one deed.
        self._conn.execute(
            """
            UPDATE mining_drops
            SET result = 'hit',
                result_event_id = ?,
                result_observed_ts_ms = ?,
                hit_id = ?,
                hit_event_id = ?,
                resource_name = ?,
                size_label = ?,
                size_index = ?,
                expected_expires_ts_ms = ?,
                range_m = ?,
                depth_m = ?
            WHERE drop_id = ?
            """,
            (
                event_id,
                event.observed_ts_ms,
                event.hit_id,
                event_id,
                event.resource_name,
                event.size_label,
                event.size_index,
                event.expected_expires_ts_ms,
                event.range_m,
                event.depth_m,
                event.drop_id,
            ),
        )

    def mark_no_resources(self, *, event: MiningNoResourcesEvent, event_id: int) -> None:
        if event.drop_id is None:
            return
        self._conn.execute(
            """
            UPDATE mining_drops
            SET result = 'no_resources',
                result_event_id = ?,
                result_observed_ts_ms = ?
            WHERE drop_id = ?
            """,
            (event_id, event.observed_ts_ms, event.drop_id),
        )


def _row_to_mining_drop(row: sqlite3.Row) -> MiningDropRow:
    x = row["x"]
    y = row["y"]
    position = (
        WorldPos(
            planet_name=row["planet_name"],
            x=int(x),
            y=int(y),
            z=int(row["z"]) if row["z"] is not None else None,
        )
        if x is not None and y is not None
        else None
    )
    return MiningDropRow(
        drop_id=str(row["drop_id"]),
        drop_event_id=int(row["drop_event_id"]),
        observed_ts_ms=int(row["observed_ts_ms"]),
        position=position,
        drop_radius_m=float(row["drop_radius_m"]),
        modes_mask=_optional_int(row["modes_mask"]),
        probes_per_drop=_optional_int(row["probes_per_drop"]),
        ammo_per_drop=_optional_int(row["ammo_per_drop"]),
        ammo_cost_mpec=Mpec(int(row["ammo_cost_mpec"])),
        probes_cost_mpec=Mpec(int(row["probes_cost_mpec"])),
        finder_decay_mpec=Mpec(int(row["finder_decay_mpec"])),
        finder_enhancer_decay_mpec=Mpec(int(row["finder_enhancer_decay_mpec"])),
        amp_decay_mpec=Mpec(int(row["amp_decay_mpec"])),
        total_cost_mpec=Mpec(int(row["total_cost_mpec"])),
        result=cast(MiningDropResult, row["result"]),
        result_event_id=_optional_int(row["result_event_id"]),
        result_observed_ts_ms=_optional_int(row["result_observed_ts_ms"]),
        hit_id=row["hit_id"],
        hit_event_id=_optional_int(row["hit_event_id"]),
        resource_name=row["resource_name"],
        size_label=row["size_label"],
        size_index=_optional_int(row["size_index"]),
        expected_expires_ts_ms=_optional_int(row["expected_expires_ts_ms"]),
        range_m=_optional_float(row["range_m"]),
        depth_m=_optional_float(row["depth_m"]),
    )


def _optional_int(value: Any) -> int | None:
    return int(value) if value is not None else None


def _optional_float(value: Any) -> float | None:
    return float(value) if value is not None else None
