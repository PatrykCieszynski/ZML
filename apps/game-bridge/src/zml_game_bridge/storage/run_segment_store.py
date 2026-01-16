# zml_game_bridge/storage/run_segment_store.py
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from zml_game_bridge.common.types import Mpec


@dataclass(frozen=True, slots=True)
class RunSegmentRow:
    segment_id: int
    run_id: int
    kind: str
    label: str
    qty: int
    unit_cost_mpec: Mpec
    total_cost_mpec: Mpec
    is_active: bool
    meta: Mapping[str, Any]
    sort_key: int
    created_ts_ms: int
    updated_ts_ms: int


class RunSegmentStore:
    """
    Storage access for run_segments table.
    Assumption: used from a single-writer DB thread.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(
        self,
        *,
        run_id: int,
        kind: str,
        label: str,
        qty: int,
        unit_cost_mpec: Mpec,
        is_active: bool,
        meta: Mapping[str, Any],
        sort_key: int,
        ts_ms: int,
    ) -> int:
        """Insert segment, return segment_id."""
        raise NotImplementedError

    def get(self, segment_id: int) -> RunSegmentRow | None:
        """Return segment or None."""
        raise NotImplementedError

    def list_for_run(self, run_id: int, *, include_inactive: bool = True) -> list[RunSegmentRow]:
        """List segments ordered by sort_key,segment_id."""
        raise NotImplementedError

    def update(
        self,
        segment_id: int,
        *,
        kind: str | None = None,
        label: str | None = None,
        qty: int | None = None,
        unit_cost_mpec: Mpec | None = None,
        is_active: bool | None = None,
        meta: Mapping[str, Any] | None = None,
        sort_key: int | None = None,
        ts_ms: int,
    ) -> None:
        """Patch update + updated_ts_ms."""
        raise NotImplementedError

    def delete(self, segment_id: int) -> None:
        """Delete segment."""
        raise NotImplementedError

    def reorder(self, run_id: int, *, ordered_segment_ids: list[int], ts_ms: int) -> None:
        """
        Apply ordering by updating sort_key.
        Must validate all ids belong to run_id.
        """
        raise NotImplementedError

    def calc_total_cost_mpec(self, run_id: int) -> Mpec:
        """SUM(total_cost_mpec) for active segments."""
        raise NotImplementedError

    # Optional helpers (you'll probably want them)
    def set_active(self, segment_id: int, *, is_active: bool, ts_ms: int) -> None:
        """Toggle segment active flag."""
        raise NotImplementedError

    def clone_to_run(
        self,
        segment_id: int,
        *,
        target_run_id: int,
        ts_ms: int,
        overrides: Mapping[str, Any] | None = None,
    ) -> int:
        """
        Duplicate segment into another run (or same run).
        Overrides is a shallow dict for fields like label/qty/unit_cost/meta/sort_key.
        """
        raise NotImplementedError
