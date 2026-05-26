from __future__ import annotations

import time
from pathlib import Path

from zml_game_bridge.application.mining import MiningCoordinator
from zml_game_bridge.application.mining.claims.lifecycle import ActiveClaim
from zml_game_bridge.persistence.mining_claims import MiningClaimReader
from zml_game_bridge.persistence.schema import ensure_schema
from zml_game_bridge.persistence.sqlite import open_read_connection, open_writer_connection


class MiningLifecycleRestorer:
    """Restores volatile mining lifecycle state from durable read models."""

    def __init__(self, *, db_path: Path, mining_coordinator: MiningCoordinator) -> None:
        self._db_path = db_path
        self._mining_coordinator = mining_coordinator

    def restore(self) -> None:
        conn = open_writer_connection(self._db_path)
        try:
            ensure_schema(conn)
        finally:
            conn.close()

        conn = open_read_connection(self._db_path)
        try:
            rows = MiningClaimReader(conn).list_active(now_ts_ms=_now_ms())
        finally:
            conn.close()

        self._mining_coordinator.restore_active_claims(
            ActiveClaim(
                claim_id=row.claim_id,
                drop_id=row.drop_id,
                hit_id=row.hit_id,
                position=row.position,
                search_radius_m=row.search_radius_m,
            )
            for row in rows
        )


def _now_ms() -> int:
    return time.time_ns() // 1_000_000
