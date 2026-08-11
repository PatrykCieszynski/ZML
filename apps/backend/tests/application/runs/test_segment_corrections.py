from __future__ import annotations

import sqlite3
from pathlib import Path

from zml_backend.application.mining.segments.session import (
    MiningSegmentSetup,
    mining_segment_setup_hash,
    mining_segment_setup_snapshot,
)
from zml_backend.application.runs.segment_corrections import (
    MoveRunSegmentCommand,
    SplitRunSegmentCommand,
    UpdateRunSegmentSetupCommand,
)
from zml_backend.domain.mining_cost import MiningEquipmentProfile, MiningToolProfile
from zml_backend.domain.money import Mpec
from zml_backend.persistence.run_state import RunState
from zml_backend.persistence.runs import RunSegmentStore, RunStore
from zml_backend.persistence.schema import ensure_schema
from zml_backend.persistence.sqlite import open_sqlite


def test_update_segment_amp_recalculates_persisted_drop_cost(tmp_path: Path) -> None:
    conn = _open_test_db(tmp_path)
    try:
        run_id = _create_run(conn)
        _create_segment(conn, run_id=run_id, segment_id="segment-1", setup=_setup(amp_decay=200))
        _insert_drop(conn, run_id=run_id, segment_id="segment-1", drop_id="drop-1", ts_ms=1_000)

        updated = UpdateRunSegmentSetupCommand(
            run_id=run_id,
            segment_id="segment-1",
            amp_set=True,
            amp=None,
        ).execute(conn)

        drop = conn.execute(
            "SELECT amp_decay_mpec, total_tt_cost_mpec, total_cost_mpec FROM mining_drops WHERE drop_id = ?",
            ("drop-1",),
        ).fetchone()
        assert drop is not None
        assert drop["amp_decay_mpec"] == 0
        assert drop["total_tt_cost_mpec"] == 10_100
        assert drop["total_cost_mpec"] == 10_100
        assert updated.setup_snapshot["amp"] is None
    finally:
        conn.close()


def test_split_first_drop_creates_corrected_segment_and_moves_linked_claim(tmp_path: Path) -> None:
    conn = _open_test_db(tmp_path)
    try:
        run_id = _create_run(conn)
        _create_segment(conn, run_id=run_id, segment_id="segment-1", setup=_setup(amp_decay=200))
        for index, ts_ms in enumerate((1_000, 2_000, 3_000), start=1):
            _insert_drop(
                conn,
                run_id=run_id,
                segment_id="segment-1",
                drop_id=f"drop-{index}",
                ts_ms=ts_ms,
            )
        _insert_claim(
            conn,
            run_id=run_id,
            segment_id="segment-1",
            drop_id="drop-1",
            claim_id="claim-1",
            ts_ms=1_100,
        )

        created = SplitRunSegmentCommand(
            run_id=run_id,
            segment_id="segment-1",
            selection="first",
            drop_count=1,
            new_segment_id="segment-split",
            amp_set=True,
            amp=None,
        ).execute(conn)

        assignments = {
            str(row["drop_id"]): str(row["segment_id"])
            for row in conn.execute(
                "SELECT drop_id, segment_id FROM mining_drops ORDER BY observed_ts_ms"
            ).fetchall()
        }
        claim = conn.execute(
            "SELECT segment_id FROM mining_claims WHERE claim_id = ?",
            ("claim-1",),
        ).fetchone()
        source = RunSegmentStore(conn).get("segment-1")
        split_drop = conn.execute(
            "SELECT amp_decay_mpec, total_tt_cost_mpec FROM mining_drops WHERE drop_id = ?",
            ("drop-1",),
        ).fetchone()

        assert assignments == {
            "drop-1": "segment-split",
            "drop-2": "segment-1",
            "drop-3": "segment-1",
        }
        assert claim is not None and claim["segment_id"] == "segment-split"
        assert source is not None
        assert created.segment_index == 1
        assert source.segment_index == 2
        assert source.started_ts_ms == 2_000
        assert created.setup_snapshot["amp"] is None
        assert split_drop is not None
        assert split_drop["amp_decay_mpec"] == 0
        assert split_drop["total_tt_cost_mpec"] == 10_100
    finally:
        conn.close()


def test_move_active_segment_to_new_run_switches_active_run_and_assignments(tmp_path: Path) -> None:
    conn = _open_test_db(tmp_path)
    try:
        run_id = _create_run(conn)
        RunState(conn).set_active_run(run_id)
        _create_segment(conn, run_id=run_id, segment_id="segment-1", setup=_setup(amp_decay=200))
        _insert_drop(conn, run_id=run_id, segment_id="segment-1", drop_id="drop-1", ts_ms=1_000)
        _insert_claim(
            conn,
            run_id=run_id,
            segment_id="segment-1",
            drop_id="drop-1",
            claim_id="claim-1",
            ts_ms=1_100,
        )

        moved = MoveRunSegmentCommand(
            run_id=run_id,
            segment_id="segment-1",
            new_run_name="Corrected run",
        ).execute(conn)

        target_run = RunStore(conn).get_run(moved.run_id)
        source_run = RunStore(conn).get_run(run_id)
        drop = conn.execute(
            "SELECT run_id FROM mining_drops WHERE drop_id = ?",
            ("drop-1",),
        ).fetchone()
        claim = conn.execute(
            "SELECT run_id FROM mining_claims WHERE claim_id = ?",
            ("claim-1",),
        ).fetchone()

        assert moved.run_id != run_id
        assert moved.status == "active"
        assert target_run is not None and target_run.name == "Corrected run"
        assert target_run.status == "running"
        assert source_run is not None and source_run.status == "stopped"
        assert RunState(conn).try_get_active_run_id() == moved.run_id
        assert drop is not None and drop["run_id"] == moved.run_id
        assert claim is not None and claim["run_id"] == moved.run_id
    finally:
        conn.close()


def _open_test_db(tmp_path: Path) -> sqlite3.Connection:
    conn = open_sqlite(tmp_path / "segment-corrections.sqlite3")
    ensure_schema(conn)
    return conn


def _create_run(conn: sqlite3.Connection) -> int:
    return RunStore(conn).create_run(name="Run", notes=None, ts_ms=500, status="running")


def _setup(*, amp_decay: int) -> MiningSegmentSetup:
    return MiningSegmentSetup(
        profile=MiningEquipmentProfile(
            finder=MiningToolProfile(
                name="Rookie",
                decay_mpec=Mpec(100),
                radius_m=55.0,
            ),
            amp=MiningToolProfile(name="Terra", decay_mpec=Mpec(amp_decay)),
        ),
        modes_mask=1,
        ammo_per_drop=1_000,
        probes_per_drop=None,
    )


def _create_segment(
    conn: sqlite3.Connection,
    *,
    run_id: int,
    segment_id: str,
    setup: MiningSegmentSetup,
) -> None:
    RunSegmentStore(conn).create(
        run_id=run_id,
        segment_id=segment_id,
        segment_index=1,
        started_ts_ms=1_000,
        setup_hash=mining_segment_setup_hash(setup),
        setup_snapshot=mining_segment_setup_snapshot(setup),
        ts_ms=500,
    )


def _insert_drop(
    conn: sqlite3.Connection,
    *,
    run_id: int,
    segment_id: str,
    drop_id: str,
    ts_ms: int,
) -> None:
    event_id = _insert_event(
        conn,
        run_id=run_id,
        segment_id=segment_id,
        event_type="MiningDropEvent",
        ts_ms=ts_ms,
    )
    conn.execute(
        """
        INSERT INTO mining_drops (
            drop_id, drop_event_id, run_id, segment_id, observed_ts_ms,
            drop_radius_m, modes_mask, probes_per_drop, ammo_per_drop,
            ammo_cost_mpec, probes_cost_mpec, finder_decay_mpec,
            finder_enhancer_decay_mpec, amp_decay_mpec,
            total_tt_cost_mpec, total_cost_mpec, result
        )
        VALUES (?, ?, ?, ?, ?, 55.0, 1, NULL, 1000, 10000, 0, 100, 0, 200, 10300, 10300, 'pending')
        """,
        (drop_id, event_id, run_id, segment_id, ts_ms),
    )


def _insert_claim(
    conn: sqlite3.Connection,
    *,
    run_id: int,
    segment_id: str,
    drop_id: str,
    claim_id: str,
    ts_ms: int,
) -> None:
    event_id = _insert_event(
        conn,
        run_id=run_id,
        segment_id=segment_id,
        event_type="MiningClaimCreatedEvent",
        ts_ms=ts_ms,
    )
    conn.execute(
        """
        INSERT INTO mining_claims (
            claim_id, created_event_id, drop_id, run_id, segment_id,
            observed_ts_ms, search_radius_m, resource_name, mining_type, status
        )
        VALUES (?, ?, ?, ?, ?, ?, 55.0, 'Lysterium Stone', 'ore', 'active')
        """,
        (claim_id, event_id, drop_id, run_id, segment_id, ts_ms),
    )


def _insert_event(
    conn: sqlite3.Connection,
    *,
    run_id: int,
    segment_id: str,
    event_type: str,
    ts_ms: int,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO events (created_ts_ms, event_type, payload_json, run_id, segment_id)
        VALUES (?, ?, '{}', ?, ?)
        """,
        (ts_ms, event_type, run_id, segment_id),
    )
    assert cur.lastrowid is not None
    return int(cur.lastrowid)
