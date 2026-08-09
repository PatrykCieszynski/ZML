from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from zml_backend.application.mining.settings import IdFactory
from zml_backend.domain.mining_cost import MiningEquipmentProfile, MiningToolProfile
from zml_backend.domain.mining_events import RunSegmentEndedEvent, RunSegmentStartedEvent
from zml_backend.domain.money import mpec_to_int
from zml_backend.persistence.sqlite import open_read_connection

logger = logging.getLogger(__name__)

ACTIVE_RUN_ID_KEY = "active_run_id"


@dataclass(frozen=True, slots=True)
class DropRunContext:
    run_id: int | None
    segment_id: str | None
    lifecycle_events: tuple[RunSegmentEndedEvent | RunSegmentStartedEvent, ...] = ()


@dataclass(frozen=True, slots=True)
class MiningSegmentSetup:
    profile: MiningEquipmentProfile
    modes_mask: int | None
    ammo_per_drop: int | None
    probes_per_drop: int | None


@dataclass(frozen=True, slots=True)
class ActiveSegmentState:
    segment_id: str
    segment_index: int
    setup_hash: str


class RunSessionService:
    """
    Assigns mining drops to setup buckets inside the active run.

    The service reads the active run pointer from SQLite, but segment creation is
    emitted as durable events. The DB writer persists those events and projects
    the run_segments table, keeping drop/segment writes on the same path.
    """

    def __init__(
        self,
        *,
        db_path: Path,
        id_factory: IdFactory,
        connect: Callable[[Path], sqlite3.Connection] | None = None,
    ) -> None:
        self._db_path = db_path
        self._id_factory = id_factory
        self._connect = connect or _default_connect
        self._lock = threading.RLock()
        self._active_run_id: int | None = None
        self._segments_by_setup_hash: dict[str, ActiveSegmentState] = {}
        self._last_segment_id: str | None = None
        self._next_segment_index = 1

    def context_for_drop(
        self,
        *,
        observed_ts_ms: int,
        setup: MiningSegmentSetup,
    ) -> DropRunContext:
        setup_snapshot = mining_segment_setup_snapshot(setup)
        setup_json = _stable_json(setup_snapshot)
        setup_hash = _setup_hash(setup_json)

        with self._lock:
            run_id = self._load_active_run_id()
            if run_id is None:
                self._reset_run_segments()
                return DropRunContext(run_id=None, segment_id=None)

            lifecycle_events: list[RunSegmentEndedEvent | RunSegmentStartedEvent] = []
            if run_id != self._active_run_id:
                self._active_run_id = run_id
                self._next_segment_index = self._load_next_segment_index(run_id)
                self._segments_by_setup_hash = self._load_segments_by_setup_hash(run_id)

            segment = self._segments_by_setup_hash.get(setup_hash)
            if segment is None:
                segment = ActiveSegmentState(
                    segment_id=self._id_factory(),
                    segment_index=self._next_segment_index,
                    setup_hash=setup_hash,
                )
                segment_index = self._next_segment_index
                self._next_segment_index += 1
                self._segments_by_setup_hash[setup_hash] = segment
                lifecycle_events.append(
                    RunSegmentStartedEvent(
                        segment_id=segment.segment_id,
                        run_id=run_id,
                        segment_index=segment_index,
                        started_ts_ms=observed_ts_ms,
                        setup_hash=setup_hash,
                        setup_snapshot=setup_snapshot,
                    )
                )
                logger.info(
                    "run_segment_started segment_id=%s run_id=%s segment_index=%s setup_hash=%s",
                    segment.segment_id,
                    run_id,
                    segment_index,
                    setup_hash,
                )

            self._last_segment_id = segment.segment_id
            return DropRunContext(
                run_id=run_id,
                segment_id=segment.segment_id,
                lifecycle_events=tuple(lifecycle_events),
            )

    def current_run_id(self) -> int | None:
        with self._lock:
            run_id = self._load_active_run_id()
            if run_id is None:
                self._reset_run_segments()
            return run_id

    def current_segment_id(self) -> str | None:
        with self._lock:
            run_id = self._load_active_run_id()
            if run_id is None:
                self._reset_run_segments()
                return None
            if run_id != self._active_run_id:
                self._active_run_id = run_id
                self._segments_by_setup_hash = self._load_segments_by_setup_hash(run_id)
                self._last_segment_id = None
                self._next_segment_index = self._load_next_segment_index(run_id)
            return self._last_segment_id

    def _reset_run_segments(self) -> None:
        self._active_run_id = None
        self._segments_by_setup_hash = {}
        self._last_segment_id = None
        self._next_segment_index = 1

    def _load_active_run_id(self) -> int | None:
        conn = self._connect(self._db_path)
        try:
            cur = conn.execute(
                """
                SELECT runs.run_id
                FROM app_state
                JOIN runs ON runs.run_id = CAST(app_state.value AS INTEGER)
                WHERE app_state.key = ? AND runs.status = 'running'
                """,
                (ACTIVE_RUN_ID_KEY,),
            )
            row = cur.fetchone()
            return int(row["run_id"]) if row is not None else None
        finally:
            conn.close()

    def _load_next_segment_index(self, run_id: int) -> int:
        conn = self._connect(self._db_path)
        try:
            cur = conn.execute(
                "SELECT COALESCE(MAX(segment_index), 0) AS max_index FROM run_segments WHERE run_id = ?",
                (run_id,),
            )
            row = cur.fetchone()
            return int(row["max_index"]) + 1
        finally:
            conn.close()

    def _load_segments_by_setup_hash(self, run_id: int) -> dict[str, ActiveSegmentState]:
        conn = self._connect(self._db_path)
        try:
            cur = conn.execute(
                """
                SELECT segment_id, segment_index, setup_hash
                FROM run_segments
                WHERE run_id = ?
                ORDER BY segment_index ASC, started_ts_ms ASC, segment_id ASC
                """,
                (run_id,),
            )
            segments: dict[str, ActiveSegmentState] = {}
            for row in cur.fetchall():
                segment = ActiveSegmentState(
                    segment_id=str(row["segment_id"]),
                    segment_index=int(row["segment_index"]),
                    setup_hash=str(row["setup_hash"]),
                )
                segments[segment.setup_hash] = segment
            return segments
        finally:
            conn.close()


def mining_segment_setup_snapshot(setup: MiningSegmentSetup) -> dict[str, object]:
    """Snapshot fields that define mining drop segment boundaries.

    Extractor is intentionally excluded: it affects extraction cost, but should
    not split a drop segment.
    """
    profile = setup.profile
    return {
        "finder": _tool_snapshot(profile.finder),
        "amp": _tool_snapshot(profile.amp),
        "modes_mask": setup.modes_mask,
        "ammo_per_drop": setup.ammo_per_drop,
        "probes_per_drop": setup.probes_per_drop,
        "finder_range_enhancers": {
            "count": profile.finder_range_enhancers.count,
            "decay_bonus_per_enhancer_ppm": profile.finder_range_enhancers.decay_bonus_per_enhancer.ppm,
            "radius_bonus_per_enhancer_ppm": profile.finder_range_enhancers.radius_bonus_per_enhancer.ppm,
        },
        "fallback_ammo_per_drop": profile.fallback_ammo_per_drop,
        "fallback_probes_per_drop": profile.fallback_probes_per_drop,
    }


def _tool_snapshot(tool: MiningToolProfile | None) -> dict[str, object] | None:
    if tool is None:
        return None
    return {
        "name": tool.name,
        "decay_mpec": mpec_to_int(tool.decay_mpec),
        "markup_ppm": tool.markup.ppm,
        "radius_m": tool.radius_m,
    }


def _stable_json(value: dict[str, object]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _setup_hash(setup_json: str) -> str:
    return hashlib.sha256(setup_json.encode("utf-8")).hexdigest()[:16]


def _default_connect(path: Path) -> sqlite3.Connection:
    return open_read_connection(path)
