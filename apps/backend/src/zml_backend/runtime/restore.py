from __future__ import annotations

from pathlib import Path

from zml_backend.application.mining import MiningCoordinator
from zml_backend.application.mining.claims.lifecycle import ActiveClaim
from zml_backend.persistence.mining_claims import MiningClaimReader
from zml_backend.persistence.schema import ensure_schema
from zml_backend.persistence.sqlite import open_read_connection, open_writer_connection


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
        self.restore_active_claims()

    def restore_active_claims(self) -> None:
        conn = open_read_connection(self._db_path)
        try:
            rows = MiningClaimReader(conn).list_active()
        finally:
            conn.close()

        self._mining_coordinator.restore_active_claims(
            ActiveClaim(
                claim_id=row.claim_id,
                drop_id=row.drop_id,
                hit_id=row.hit_id,
                run_id=row.run_id,
                segment_id=row.segment_id,
                position=row.position,
                search_radius_m=row.search_radius_m,
                expected_expires_ts_ms=row.expected_expires_ts_ms,
                observed_ts_ms=row.observed_ts_ms,
                resource_name=row.resource_name,
                mining_type=row.mining_type,
            )
            for row in rows
        )
