from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, cast

from zml_game_bridge.domain.mining_events import (
    MiningClaimCreatedEvent,
    MiningClaimDepletedEvent,
)
from zml_game_bridge.domain.position import WorldPos
from zml_game_bridge.events.base import EventBase
from zml_game_bridge.events.envelope import EventEnvelope
from zml_game_bridge.persistence.event_projector import EventProjector

MiningClaimStatus = Literal["active", "depleted"]


@dataclass(frozen=True, slots=True)
class MiningClaimRow:
    claim_id: str
    created_event_id: int
    hit_id: str | None
    drop_id: str | None
    run_id: int | None
    segment_id: str | None
    observed_ts_ms: int
    position: WorldPos | None
    search_radius_m: float | None
    resource_name: str | None
    mining_type: str | None
    size_label: str | None
    size_index: int | None
    expected_expires_ts_ms: int | None
    range_m: float | None
    depth_m: float | None
    status: MiningClaimStatus
    depleted_event_id: int | None
    depleted_event_dt: datetime | None
    depleted_position: WorldPos | None
    depleted_distance_m: float | None


class MiningClaimReader:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, claim_id: str) -> MiningClaimRow | None:
        cur = self._conn.execute(
            """
            SELECT *
            FROM mining_claims
            WHERE claim_id = ?
            """,
            (claim_id,),
        )
        row = cur.fetchone()
        return _row_to_mining_claim(row) if row is not None else None

    def list_active(
        self,
        *,
        now_ts_ms: int | None = None,
        run_id: int | None = None,
    ) -> list[MiningClaimRow]:
        filters = ["status = 'active'"]
        params: list[int] = []
        if now_ts_ms is not None:
            filters.append("(expected_expires_ts_ms IS NULL OR expected_expires_ts_ms > ?)")
            params.append(now_ts_ms)
        if run_id is not None:
            filters.append("run_id = ?")
            params.append(run_id)
        cur = self._conn.execute(
            f"""
            SELECT *
            FROM mining_claims
            WHERE {" AND ".join(filters)}
            ORDER BY observed_ts_ms ASC, created_event_id ASC
            """,
            params,
        )
        return [_row_to_mining_claim(row) for row in cur.fetchall()]

    def list_all(self, *, run_id: int | None = None) -> list[MiningClaimRow]:
        where_clause = "" if run_id is None else "WHERE run_id = ?"
        params: tuple[int, ...] = () if run_id is None else (run_id,)
        cur = self._conn.execute(
            f"""
            SELECT *
            FROM mining_claims
            {where_clause}
            ORDER BY observed_ts_ms DESC, created_event_id DESC
            """,
            params,
        )
        return [_row_to_mining_claim(row) for row in cur.fetchall()]


class MiningClaimProjector(EventProjector):
    def project(
        self,
        *,
        conn: sqlite3.Connection,
        event: EventBase,
        envelope: EventEnvelope,
    ) -> None:
        writer = _MiningClaimProjectionWriter(conn)
        if isinstance(event, MiningClaimCreatedEvent):
            writer.upsert_claim(event=event, event_id=envelope.event_id)
        elif isinstance(event, MiningClaimDepletedEvent):
            writer.mark_depleted(event=event, event_id=envelope.event_id)


class _MiningClaimProjectionWriter:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def upsert_claim(self, *, event: MiningClaimCreatedEvent, event_id: int) -> None:
        position = event.position
        self._conn.execute(
            """
            INSERT INTO mining_claims (
                claim_id, created_event_id, hit_id, drop_id, run_id, segment_id, observed_ts_ms,
                planet_name, x, y, z, search_radius_m,
                resource_name, mining_type, size_label, size_index, expected_expires_ts_ms,
                range_m, depth_m, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
            ON CONFLICT(claim_id) DO UPDATE SET
                created_event_id = excluded.created_event_id,
                hit_id = excluded.hit_id,
                drop_id = excluded.drop_id,
                run_id = excluded.run_id,
                segment_id = excluded.segment_id,
                observed_ts_ms = excluded.observed_ts_ms,
                planet_name = excluded.planet_name,
                x = excluded.x,
                y = excluded.y,
                z = excluded.z,
                search_radius_m = excluded.search_radius_m,
                resource_name = excluded.resource_name,
                mining_type = excluded.mining_type,
                size_label = excluded.size_label,
                size_index = excluded.size_index,
                expected_expires_ts_ms = excluded.expected_expires_ts_ms,
                range_m = excluded.range_m,
                depth_m = excluded.depth_m,
                status = 'active',
                depleted_event_id = NULL,
                depleted_event_dt = NULL,
                depleted_planet_name = NULL,
                depleted_x = NULL,
                depleted_y = NULL,
                depleted_z = NULL,
                depleted_distance_m = NULL
            """,
            (
                event.claim_id,
                event_id,
                event.hit_id,
                event.drop_id,
                event.run_id,
                event.segment_id,
                event.observed_ts_ms,
                position.planet_name if position is not None else None,
                position.x if position is not None else None,
                position.y if position is not None else None,
                position.z if position is not None else None,
                event.search_radius_m,
                event.resource_name,
                event.mining_type,
                event.size_label,
                event.size_index,
                event.expected_expires_ts_ms,
                event.range_m,
                event.depth_m,
            ),
        )

    def mark_depleted(self, *, event: MiningClaimDepletedEvent, event_id: int) -> None:
        position = event.position
        self._conn.execute(
            """
            UPDATE mining_claims
            SET status = 'depleted',
                depleted_event_id = ?,
                depleted_event_dt = ?,
                depleted_planet_name = ?,
                depleted_x = ?,
                depleted_y = ?,
                depleted_z = ?,
                depleted_distance_m = ?
            WHERE claim_id = ?
            """,
            (
                event_id,
                event.event_dt.isoformat(),
                position.planet_name,
                position.x,
                position.y,
                position.z,
                event.distance_m,
                event.claim_id,
            ),
        )


def _row_to_mining_claim(row: sqlite3.Row) -> MiningClaimRow:
    return MiningClaimRow(
        claim_id=str(row["claim_id"]),
        created_event_id=int(row["created_event_id"]),
        hit_id=row["hit_id"],
        drop_id=row["drop_id"],
        run_id=_optional_int(row["run_id"]),
        segment_id=row["segment_id"],
        observed_ts_ms=int(row["observed_ts_ms"]),
        position=_position_from_row(row, "", "planet_name"),
        search_radius_m=_optional_float(row["search_radius_m"]),
        resource_name=row["resource_name"],
        mining_type=row["mining_type"],
        size_label=row["size_label"],
        size_index=_optional_int(row["size_index"]),
        expected_expires_ts_ms=_optional_int(row["expected_expires_ts_ms"]),
        range_m=_optional_float(row["range_m"]),
        depth_m=_optional_float(row["depth_m"]),
        status=cast(MiningClaimStatus, row["status"]),
        depleted_event_id=_optional_int(row["depleted_event_id"]),
        depleted_event_dt=_optional_datetime(row["depleted_event_dt"]),
        depleted_position=_position_from_row(row, "depleted_", "depleted_planet_name"),
        depleted_distance_m=_optional_float(row["depleted_distance_m"]),
    )


def _position_from_row(
    row: sqlite3.Row,
    prefix: str,
    planet_column: str,
) -> WorldPos | None:
    x = row[f"{prefix}x"]
    y = row[f"{prefix}y"]
    return (
        WorldPos(
            planet_name=row[planet_column],
            x=int(x),
            y=int(y),
            z=int(row[f"{prefix}z"]) if row[f"{prefix}z"] is not None else None,
        )
        if x is not None and y is not None
        else None
    )


def _optional_int(value: Any) -> int | None:
    return int(value) if value is not None else None


def _optional_float(value: Any) -> float | None:
    return float(value) if value is not None else None


def _optional_datetime(value: Any) -> datetime | None:
    return datetime.fromisoformat(str(value)) if value is not None else None
