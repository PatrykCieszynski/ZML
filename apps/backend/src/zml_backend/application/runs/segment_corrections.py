from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, cast

from zml_backend.application.mining.segments.session import (
    MiningSegmentSetup,
    mining_segment_setup_hash,
    mining_segment_setup_snapshot,
)
from zml_backend.domain.mining_cost import (
    FinderRangeEnhancerLoadout,
    MiningEquipmentProfile,
    MiningToolProfile,
    calculate_drop_cost,
    effective_finder_radius_m,
)
from zml_backend.domain.money import Mpec, mpec_to_int
from zml_backend.domain.rate import Rate
from zml_backend.persistence.run_state import RunState
from zml_backend.persistence.runs import RunSegmentRow, RunSegmentStore, RunStore
from zml_backend.runtime.db_commands import DbCommand

SegmentSplitSelection = Literal["first", "last"]


class SegmentCorrectionError(Exception):
    pass


class SegmentNotFoundError(SegmentCorrectionError):
    def __init__(self, segment_id: str) -> None:
        super().__init__(f"Segment not found: {segment_id}")
        self.segment_id = segment_id


class InvalidSegmentCorrectionError(SegmentCorrectionError):
    pass


@dataclass(frozen=True, slots=True)
class UpdateRunSegmentSetupCommand(DbCommand[RunSegmentRow]):
    run_id: int
    segment_id: str
    finder_set: bool = False
    finder: MiningToolProfile | None = None
    amp_set: bool = False
    amp: MiningToolProfile | None = None

    def execute(self, conn: sqlite3.Connection) -> RunSegmentRow:
        segment = _require_segment(conn, run_id=self.run_id, segment_id=self.segment_id)
        setup = _patched_setup(
            _setup_from_snapshot(segment.setup_snapshot),
            finder_set=self.finder_set,
            finder=self.finder,
            amp_set=self.amp_set,
            amp=self.amp,
        )
        _update_segment_setup(conn, segment_id=self.segment_id, setup=setup, ts_ms=_now_ms())
        _recalculate_segment_drops(conn, segment_id=self.segment_id, setup=setup)
        updated = RunSegmentStore(conn).get(self.segment_id)
        if updated is None:
            raise RuntimeError("Segment disappeared after setup correction")
        return updated


@dataclass(frozen=True, slots=True)
class SplitRunSegmentCommand(DbCommand[RunSegmentRow]):
    run_id: int
    segment_id: str
    selection: SegmentSplitSelection
    drop_count: int
    new_segment_id: str
    finder_set: bool = False
    finder: MiningToolProfile | None = None
    amp_set: bool = False
    amp: MiningToolProfile | None = None

    def execute(self, conn: sqlite3.Connection) -> RunSegmentRow:
        source = _require_segment(conn, run_id=self.run_id, segment_id=self.segment_id)
        drops = conn.execute(
            """
            SELECT drop_id, observed_ts_ms
            FROM mining_drops
            WHERE run_id = ? AND segment_id = ?
            ORDER BY observed_ts_ms ASC, drop_event_id ASC
            """,
            (self.run_id, self.segment_id),
        ).fetchall()
        if len(drops) < 2:
            raise InvalidSegmentCorrectionError("A segment needs at least two drops to be split")
        if self.drop_count <= 0 or self.drop_count >= len(drops):
            raise InvalidSegmentCorrectionError(
                f"Split drop count must be between 1 and {len(drops) - 1}"
            )
        if self.selection not in ("first", "last"):
            raise InvalidSegmentCorrectionError(f"Unsupported split selection: {self.selection}")

        selected = (
            drops[: self.drop_count] if self.selection == "first" else drops[-self.drop_count :]
        )
        remaining = (
            drops[self.drop_count :] if self.selection == "first" else drops[: -self.drop_count]
        )
        selected_drop_ids = [str(row["drop_id"]) for row in selected]

        corrected_setup = _patched_setup(
            _setup_from_snapshot(source.setup_snapshot),
            finder_set=self.finder_set,
            finder=self.finder,
            amp_set=self.amp_set,
            amp=self.amp,
        )
        ts_ms = _now_ms()
        segments = RunSegmentStore(conn).list_for_run(self.run_id)
        append_index = max((segment.segment_index for segment in segments), default=0) + 1
        RunSegmentStore(conn).create(
            run_id=self.run_id,
            segment_id=self.new_segment_id,
            segment_index=append_index,
            started_ts_ms=int(selected[0]["observed_ts_ms"]),
            setup_hash=mining_segment_setup_hash(corrected_setup),
            setup_snapshot=mining_segment_setup_snapshot(corrected_setup),
            notes=f"Split from segment #{source.segment_index}",
            ts_ms=ts_ms,
        )
        if source.status != "active" or source.ended_ts_ms is not None:
            RunSegmentStore(conn).update(
                self.new_segment_id,
                status=source.status,
                ended_ts_ms=source.ended_ts_ms,
                ts_ms=ts_ms,
            )

        _assign_drop_ids_to_segment(
            conn,
            drop_ids=selected_drop_ids,
            run_id=self.run_id,
            segment_id=self.new_segment_id,
        )
        _recalculate_segment_drops(conn, segment_id=self.new_segment_id, setup=corrected_setup)

        if self.selection == "first":
            conn.execute(
                """
                UPDATE run_segments
                SET started_ts_ms = ?, updated_ts_ms = ?
                WHERE segment_id = ?
                """,
                (int(remaining[0]["observed_ts_ms"]), ts_ms, self.segment_id),
            )

        ordered_ids = [segment.segment_id for segment in segments]
        source_position = ordered_ids.index(self.segment_id)
        insert_position = source_position if self.selection == "first" else source_position + 1
        ordered_ids.insert(insert_position, self.new_segment_id)
        RunSegmentStore(conn).reorder(self.run_id, ordered_segment_ids=ordered_ids, ts_ms=ts_ms)

        created = RunSegmentStore(conn).get(self.new_segment_id)
        if created is None:
            raise RuntimeError("Split segment was not created")
        return created


@dataclass(frozen=True, slots=True)
class MoveRunSegmentCommand(DbCommand[RunSegmentRow]):
    run_id: int
    segment_id: str
    target_run_id: int | None = None
    new_run_name: str | None = None

    def execute(self, conn: sqlite3.Connection) -> RunSegmentRow:
        _require_segment(conn, run_id=self.run_id, segment_id=self.segment_id)
        if (self.target_run_id is None) == (self.new_run_name is None):
            raise InvalidSegmentCorrectionError(
                "Choose either an existing target run or a new run name"
            )

        run_store = RunStore(conn)
        source_run = run_store.get_run(self.run_id)
        if source_run is None or source_run.status == "deleted":
            raise InvalidSegmentCorrectionError(f"Source run not found: {self.run_id}")

        state = RunState(conn)
        source_is_active = state.try_get_active_run_id() == self.run_id
        created_new_run = self.new_run_name is not None
        ts_ms = _now_ms()

        if created_new_run:
            name = cast(str, self.new_run_name).strip()
            if not name:
                raise InvalidSegmentCorrectionError("New run name must not be empty")
            target_run_id = run_store.create_run(
                name=name,
                notes=None,
                ts_ms=ts_ms,
                status="running" if source_is_active else "stopped",
            )
        else:
            target_run_id = cast(int, self.target_run_id)
            target_run = run_store.get_run(target_run_id)
            if target_run is None or target_run.status == "deleted":
                raise InvalidSegmentCorrectionError(f"Target run not found: {target_run_id}")
            if target_run_id == self.run_id:
                raise InvalidSegmentCorrectionError("Segment is already in the selected run")

        target_segments = RunSegmentStore(conn).list_for_run(target_run_id)
        target_index = max((segment.segment_index for segment in target_segments), default=0) + 1

        if created_new_run and source_is_active:
            run_store.set_run_status(self.run_id, status="stopped", ts_ms=ts_ms)
            RunSegmentStore(conn).end_active_for_run(
                self.run_id,
                ended_ts_ms=ts_ms,
                ts_ms=ts_ms,
            )

        _transfer_segment_loot_totals(
            conn,
            segment_id=self.segment_id,
            source_run_id=self.run_id,
            target_run_id=target_run_id,
        )

        conn.execute(
            """
            UPDATE run_segments
            SET run_id = ?, segment_index = ?, updated_ts_ms = ?
            WHERE segment_id = ?
            """,
            (target_run_id, target_index, ts_ms, self.segment_id),
        )
        conn.execute(
            "UPDATE mining_drops SET run_id = ? WHERE segment_id = ?",
            (target_run_id, self.segment_id),
        )
        conn.execute(
            "UPDATE mining_claims SET run_id = ? WHERE segment_id = ?",
            (target_run_id, self.segment_id),
        )
        conn.execute(
            "UPDATE events SET run_id = ? WHERE segment_id = ?",
            (target_run_id, self.segment_id),
        )
        conn.execute(
            "UPDATE mining_loot_recent SET run_id = ? WHERE segment_id = ?",
            (target_run_id, self.segment_id),
        )
        conn.execute(
            "UPDATE segment_item_totals SET run_id = ? WHERE segment_id = ?",
            (target_run_id, self.segment_id),
        )

        _reindex_run_segments(conn, run_id=self.run_id, ts_ms=ts_ms)
        _reindex_run_segments(conn, run_id=target_run_id, ts_ms=ts_ms)

        if created_new_run and source_is_active:
            conn.execute(
                """
                UPDATE run_segments
                SET status = 'active', ended_ts_ms = NULL, updated_ts_ms = ?
                WHERE segment_id = ?
                """,
                (ts_ms, self.segment_id),
            )
            state.set_active_run(target_run_id)

        moved = RunSegmentStore(conn).get(self.segment_id)
        if moved is None:
            raise RuntimeError("Segment disappeared after move")
        return moved


def _require_segment(conn: sqlite3.Connection, *, run_id: int, segment_id: str) -> RunSegmentRow:
    segment = RunSegmentStore(conn).get(segment_id)
    if segment is None or segment.run_id != run_id:
        raise SegmentNotFoundError(segment_id)
    return segment


def _patched_setup(
    setup: MiningSegmentSetup,
    *,
    finder_set: bool,
    finder: MiningToolProfile | None,
    amp_set: bool,
    amp: MiningToolProfile | None,
) -> MiningSegmentSetup:
    if finder_set and finder is None:
        raise InvalidSegmentCorrectionError("A segment must have a finder")
    profile = setup.profile
    return MiningSegmentSetup(
        profile=MiningEquipmentProfile(
            finder=finder if finder_set else profile.finder,
            amp=amp if amp_set else profile.amp,
            extractor=None,
            finder_range_enhancers=profile.finder_range_enhancers,
            fallback_ammo_per_drop=profile.fallback_ammo_per_drop,
            fallback_probes_per_drop=profile.fallback_probes_per_drop,
        ),
        modes_mask=setup.modes_mask,
        ammo_per_drop=setup.ammo_per_drop,
        probes_per_drop=setup.probes_per_drop,
    )


def _setup_from_snapshot(snapshot: Mapping[str, object]) -> MiningSegmentSetup:
    finder = _tool_from_snapshot(snapshot.get("finder"), required=True)
    amp = _tool_from_snapshot(snapshot.get("amp"), required=False)
    enhancer_snapshot = snapshot.get("finder_range_enhancers")
    enhancers = _enhancers_from_snapshot(enhancer_snapshot)
    return MiningSegmentSetup(
        profile=MiningEquipmentProfile(
            finder=cast(MiningToolProfile, finder),
            amp=amp,
            finder_range_enhancers=enhancers,
            fallback_ammo_per_drop=_optional_int(snapshot.get("fallback_ammo_per_drop")),
            fallback_probes_per_drop=_optional_int(snapshot.get("fallback_probes_per_drop")),
        ),
        modes_mask=_optional_int(snapshot.get("modes_mask")),
        ammo_per_drop=_optional_int(snapshot.get("ammo_per_drop")),
        probes_per_drop=_optional_int(snapshot.get("probes_per_drop")),
    )


def _tool_from_snapshot(value: object, *, required: bool) -> MiningToolProfile | None:
    if value is None and not required:
        return None
    if not isinstance(value, Mapping):
        raise InvalidSegmentCorrectionError("Segment setup contains an invalid tool snapshot")
    item = cast(Mapping[str, object], value)
    name = item.get("name")
    decay_mpec = item.get("decay_mpec")
    markup_ppm = item.get("markup_ppm", 1_000_000)
    radius_m = item.get("radius_m")
    if (
        not isinstance(name, str)
        or not isinstance(decay_mpec, int)
        or not isinstance(markup_ppm, int)
    ):
        raise InvalidSegmentCorrectionError("Segment tool snapshot is incomplete")
    if radius_m is not None and not isinstance(radius_m, int | float):
        raise InvalidSegmentCorrectionError("Segment finder radius is invalid")
    return MiningToolProfile(
        name=name,
        decay_mpec=Mpec(decay_mpec),
        markup=Rate(markup_ppm),
        radius_m=float(radius_m) if radius_m is not None else None,
    )


def _enhancers_from_snapshot(value: object) -> FinderRangeEnhancerLoadout:
    if not isinstance(value, Mapping):
        return FinderRangeEnhancerLoadout()
    item = cast(Mapping[str, object], value)
    count = item.get("count", 0)
    decay_ppm = item.get("decay_bonus_per_enhancer_ppm", 100_000)
    radius_ppm = item.get("radius_bonus_per_enhancer_ppm", 10_000)
    return FinderRangeEnhancerLoadout(
        count=count if isinstance(count, int) else 0,
        decay_bonus_per_enhancer=Rate(decay_ppm if isinstance(decay_ppm, int) else 100_000),
        radius_bonus_per_enhancer=Rate(radius_ppm if isinstance(radius_ppm, int) else 10_000),
    )


def _update_segment_setup(
    conn: sqlite3.Connection,
    *,
    segment_id: str,
    setup: MiningSegmentSetup,
    ts_ms: int,
) -> None:
    conn.execute(
        """
        UPDATE run_segments
        SET setup_hash = ?, setup_snapshot_json = ?, updated_ts_ms = ?
        WHERE segment_id = ?
        """,
        (
            mining_segment_setup_hash(setup),
            json.dumps(
                mining_segment_setup_snapshot(setup),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
            ts_ms,
            segment_id,
        ),
    )


def _recalculate_segment_drops(
    conn: sqlite3.Connection,
    *,
    segment_id: str,
    setup: MiningSegmentSetup,
) -> None:
    rows = conn.execute(
        """
        SELECT drop_id, ammo_per_drop, probes_per_drop
        FROM mining_drops
        WHERE segment_id = ?
        """,
        (segment_id,),
    ).fetchall()
    radius_m = effective_finder_radius_m(setup.profile)
    for row in rows:
        cost = calculate_drop_cost(
            profile=setup.profile,
            ocr_ammo_per_drop=_optional_int(row["ammo_per_drop"]),
            ocr_probes_per_drop=_optional_int(row["probes_per_drop"]),
        )
        drop_id = str(row["drop_id"])
        conn.execute(
            """
            UPDATE mining_drops
            SET drop_radius_m = ?,
                ammo_cost_mpec = ?,
                probes_cost_mpec = ?,
                finder_decay_mpec = ?,
                finder_enhancer_decay_mpec = ?,
                amp_decay_mpec = ?,
                total_tt_cost_mpec = ?,
                total_cost_mpec = ?
            WHERE drop_id = ?
            """,
            (
                radius_m if radius_m is not None else 55.0,
                mpec_to_int(cost.ammo.cost_mpec),
                mpec_to_int(cost.probes.cost_mpec),
                mpec_to_int(cost.finder_decay_mpec),
                mpec_to_int(cost.finder_enhancer_decay_mpec),
                mpec_to_int(cost.amp_decay_mpec),
                mpec_to_int(cost.total_tt_mpec),
                mpec_to_int(cost.total_with_markup_mpec),
                drop_id,
            ),
        )
        conn.execute(
            """
            UPDATE mining_claims
            SET search_radius_m = ?
            WHERE drop_id = ?
            """,
            (radius_m if radius_m is not None else 55.0, drop_id),
        )


def _assign_drop_ids_to_segment(
    conn: sqlite3.Connection,
    *,
    drop_ids: Sequence[str],
    run_id: int,
    segment_id: str,
) -> None:
    placeholders = ",".join("?" for _ in drop_ids)
    conn.execute(
        f"UPDATE mining_drops SET run_id = ?, segment_id = ? WHERE drop_id IN ({placeholders})",
        (run_id, segment_id, *drop_ids),
    )
    conn.execute(
        f"""
        UPDATE mining_claims
        SET run_id = ?, segment_id = ?
        WHERE drop_id IN ({placeholders})
        """,
        (run_id, segment_id, *drop_ids),
    )


def _reindex_run_segments(conn: sqlite3.Connection, *, run_id: int, ts_ms: int) -> None:
    rows = conn.execute(
        """
        SELECT segment_id
        FROM run_segments
        WHERE run_id = ?
        ORDER BY segment_index ASC, started_ts_ms ASC, segment_id ASC
        """,
        (run_id,),
    ).fetchall()
    RunSegmentStore(conn).reorder(
        run_id,
        ordered_segment_ids=[str(row["segment_id"]) for row in rows],
        ts_ms=ts_ms,
    )


def _transfer_segment_loot_totals(
    conn: sqlite3.Connection,
    *,
    segment_id: str,
    source_run_id: int,
    target_run_id: int,
) -> None:
    totals = conn.execute(
        """
        SELECT item_name, qty, value_mpec, extraction_cost_mpec, event_count,
               first_seen_ts_ms, last_seen_ts_ms
        FROM segment_item_totals
        WHERE segment_id = ?
        """,
        (segment_id,),
    ).fetchall()
    for total in totals:
        item_name = str(total["item_name"])
        qty = int(total["qty"])
        value_mpec = int(total["value_mpec"])
        extraction_cost_mpec = int(total["extraction_cost_mpec"])
        event_count = int(total["event_count"])
        first_seen_ts_ms = int(total["first_seen_ts_ms"])
        last_seen_ts_ms = int(total["last_seen_ts_ms"])

        conn.execute(
            """
            UPDATE run_item_totals
            SET qty = qty - ?,
                value_mpec = value_mpec - ?,
                extraction_cost_mpec = extraction_cost_mpec - ?,
                event_count = event_count - ?
            WHERE run_id = ? AND item_name = ?
            """,
            (
                qty,
                value_mpec,
                extraction_cost_mpec,
                event_count,
                source_run_id,
                item_name,
            ),
        )
        conn.execute(
            """
            DELETE FROM run_item_totals
            WHERE run_id = ? AND item_name = ? AND event_count <= 0
            """,
            (source_run_id, item_name),
        )

        conn.execute(
            """
            INSERT INTO run_item_totals (
                run_id, item_name, qty, value_mpec, extraction_cost_mpec,
                event_count, first_seen_ts_ms, last_seen_ts_ms
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id, item_name) DO UPDATE SET
                qty = qty + excluded.qty,
                value_mpec = value_mpec + excluded.value_mpec,
                extraction_cost_mpec = extraction_cost_mpec + excluded.extraction_cost_mpec,
                event_count = event_count + excluded.event_count,
                first_seen_ts_ms = MIN(first_seen_ts_ms, excluded.first_seen_ts_ms),
                last_seen_ts_ms = MAX(last_seen_ts_ms, excluded.last_seen_ts_ms)
            """,
            (
                target_run_id,
                item_name,
                qty,
                value_mpec,
                extraction_cost_mpec,
                event_count,
                first_seen_ts_ms,
                last_seen_ts_ms,
            ),
        )


def _optional_int(value: object) -> int | None:
    return int(value) if isinstance(value, int) else None


def _now_ms() -> int:
    return time.time_ns() // 1_000_000
