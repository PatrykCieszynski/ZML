from __future__ import annotations

from zml_backend.persistence.cloud_sync import (
    CloudClaimSyncStore,
    CloudSyncOutcome,
)
from zml_backend.persistence.schema import ensure_schema
from zml_backend.persistence.sqlite import open_writer_connection


def test_cloud_sync_store_lists_complete_unsynced_claims_and_records_outcomes(tmp_path) -> None:
    db_path = tmp_path / "zml.sqlite3"
    conn = open_writer_connection(db_path)
    try:
        ensure_schema(conn)
        conn.executemany(
            """
            INSERT INTO events (event_id, created_ts_ms, event_type, payload_json)
            VALUES (?, ?, 'MiningClaimCreatedEvent', '{}')
            """,
            [(1, 1_000), (2, 2_000), (3, 3_000), (4, 4_000)],
        )
        conn.executemany(
            """
            INSERT INTO mining_claims (
                claim_id,
                created_event_id,
                observed_ts_ms,
                planet_name,
                x,
                y,
                resource_name,
                size_index,
                depth_m
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("claim-accepted", 1, 1_000, "Calypso", 65_000, 80_000, "Belkar Stone", 12, 812.5),
                ("claim-rejected", 2, 2_000, "Calypso", 65_100, 80_100, "Belkar Stone", 13, 740.0),
                ("claim-incomplete", 3, 3_000, "Calypso", 65_200, 80_200, None, 14, 690.0),
                ("claim-no-depth", 4, 4_000, "Calypso", 65_300, 80_300, "Belkar Stone", 15, None),
            ],
        )
        conn.commit()

        store = CloudClaimSyncStore(conn)
        pending = store.list_pending(limit=250)
        assert [claim.claim_id for claim in pending] == ["claim-accepted", "claim-rejected"]
        assert [claim.depth_m for claim in pending] == [812.5, 740.0]

        store.record_outcomes(
            (
                CloudSyncOutcome("claim-accepted", "accepted"),
                CloudSyncOutcome("claim-rejected", "rejected", "unknown_resource"),
            ),
            updated_ts_ms=5_000,
        )
        conn.commit()

        assert store.list_pending(limit=250) == []
        rows = conn.execute(
            """
            SELECT claim_id, sync_status, remote_status, reason, updated_ts_ms
            FROM cloud_claim_sync
            ORDER BY claim_id
            """
        ).fetchall()
        assert [tuple(row) for row in rows] == [
            ("claim-accepted", "synced", "accepted", None, 5_000),
            ("claim-rejected", "rejected", "rejected", "unknown_resource", 5_000),
        ]
    finally:
        conn.close()
