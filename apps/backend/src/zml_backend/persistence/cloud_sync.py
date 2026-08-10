from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Literal

CloudRemoteStatus = Literal["accepted", "already_present", "rejected"]
CloudLocalStatus = Literal["synced", "rejected"]


@dataclass(frozen=True, slots=True)
class PendingCloudClaim:
    claim_id: str
    planet_name: str
    x: int
    y: int
    resource_name: str
    size_index: int
    observed_ts_ms: int


@dataclass(frozen=True, slots=True)
class CloudSyncOutcome:
    claim_id: str
    status: CloudRemoteStatus
    reason: str | None = None


class CloudClaimSyncStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def list_pending(self, *, limit: int) -> list[PendingCloudClaim]:
        cur = self._conn.execute(
            """
            SELECT
                c.claim_id,
                c.planet_name,
                c.x,
                c.y,
                c.resource_name,
                c.size_index,
                c.observed_ts_ms
            FROM mining_claims AS c
            LEFT JOIN cloud_claim_sync AS s ON s.claim_id = c.claim_id
            WHERE s.claim_id IS NULL
              AND c.planet_name IS NOT NULL
              AND TRIM(c.planet_name) <> ''
              AND c.x IS NOT NULL
              AND c.y IS NOT NULL
              AND c.resource_name IS NOT NULL
              AND TRIM(c.resource_name) <> ''
              AND c.size_index IS NOT NULL
            ORDER BY c.observed_ts_ms ASC, c.created_event_id ASC
            LIMIT ?
            """,
            (limit,),
        )
        return [
            PendingCloudClaim(
                claim_id=str(row["claim_id"]),
                planet_name=str(row["planet_name"]),
                x=int(row["x"]),
                y=int(row["y"]),
                resource_name=str(row["resource_name"]),
                size_index=int(row["size_index"]),
                observed_ts_ms=int(row["observed_ts_ms"]),
            )
            for row in cur.fetchall()
        ]

    def record_outcomes(
        self,
        outcomes: tuple[CloudSyncOutcome, ...],
        *,
        updated_ts_ms: int,
    ) -> None:
        rows = [
            (
                outcome.claim_id,
                _local_status(outcome.status),
                outcome.status,
                outcome.reason,
                updated_ts_ms,
            )
            for outcome in outcomes
        ]
        self._conn.executemany(
            """
            INSERT INTO cloud_claim_sync (
                claim_id,
                sync_status,
                remote_status,
                reason,
                updated_ts_ms
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(claim_id) DO UPDATE SET
                sync_status = excluded.sync_status,
                remote_status = excluded.remote_status,
                reason = excluded.reason,
                updated_ts_ms = excluded.updated_ts_ms
            """,
            rows,
        )


def _local_status(remote_status: CloudRemoteStatus) -> CloudLocalStatus:
    return "rejected" if remote_status == "rejected" else "synced"
