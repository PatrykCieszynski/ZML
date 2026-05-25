from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from zml_game_bridge.domain.mining_cost import MiningEquipmentProfile, MiningToolProfile
from zml_game_bridge.domain.mining_events import RunSegmentEndedEvent, RunSegmentStartedEvent
from zml_game_bridge.domain.money import mpec_to_int
from zml_game_bridge.persistence.sqlite import open_read_connection
from zml_game_bridge.runtime.mining.settings import IdFactory

logger = logging.getLogger(__name__)

ACTIVE_RUN_ID_KEY = "active_run_id"
SETUP_CHANGED_REASON = "setup_changed"


@dataclass(frozen=True, slots=True)
class DropRunContext:
    run_id: int | None
    segment_id: str | None
    lifecycle_events: tuple[RunSegmentEndedEvent | RunSegmentStartedEvent, ...] = ()


class RunSessionService:
    """
    Tracks the current runtime segment for mining drops.

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
        self._active_segment_id: str | None = None
        self._active_setup_hash: str | None = None
        self._next_segment_index = 1

    def context_for_drop(
        self,
        *,
        observed_ts_ms: int,
        profile: MiningEquipmentProfile,
    ) -> DropRunContext:
        setup_snapshot = equipment_profile_snapshot(profile)
        setup_json = _stable_json(setup_snapshot)
        setup_hash = _setup_hash(setup_json)

        with self._lock:
            run_id = self._load_active_run_id()
            if run_id is None:
                self._reset_active_segment()
                return DropRunContext(run_id=None, segment_id=None)

            if run_id != self._active_run_id:
                self._active_run_id = run_id
                self._active_segment_id = None
                self._active_setup_hash = None
                self._next_segment_index = self._load_next_segment_index(run_id)

            lifecycle_events: list[RunSegmentEndedEvent | RunSegmentStartedEvent] = []
            if self._active_segment_id is not None and self._active_setup_hash != setup_hash:
                lifecycle_events.append(
                    RunSegmentEndedEvent(
                        segment_id=self._active_segment_id,
                        run_id=run_id,
                        ended_ts_ms=observed_ts_ms,
                        reason=SETUP_CHANGED_REASON,
                    )
                )
                self._active_segment_id = None
                self._active_setup_hash = None

            if self._active_segment_id is None:
                segment_id = self._id_factory()
                segment_index = self._next_segment_index
                self._next_segment_index += 1
                self._active_segment_id = segment_id
                self._active_setup_hash = setup_hash
                lifecycle_events.append(
                    RunSegmentStartedEvent(
                        segment_id=segment_id,
                        run_id=run_id,
                        segment_index=segment_index,
                        started_ts_ms=observed_ts_ms,
                        setup_hash=setup_hash,
                        setup_snapshot=setup_snapshot,
                    )
                )
                logger.info(
                    "run_segment_started segment_id=%s run_id=%s segment_index=%s setup_hash=%s",
                    segment_id,
                    run_id,
                    segment_index,
                    setup_hash,
                )

            return DropRunContext(
                run_id=run_id,
                segment_id=self._active_segment_id,
                lifecycle_events=tuple(lifecycle_events),
            )

    def _reset_active_segment(self) -> None:
        self._active_run_id = None
        self._active_segment_id = None
        self._active_setup_hash = None
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


def equipment_profile_snapshot(profile: MiningEquipmentProfile) -> dict[str, object]:
    return {
        "finder": _tool_snapshot(profile.finder),
        "amp": _tool_snapshot(profile.amp),
        "extractor": _tool_snapshot(profile.extractor),
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
