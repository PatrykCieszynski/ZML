from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from zml_game_bridge.domain.mining_events import (
    MiningLootItemSnapshot,
    MiningLootTotalSnapshot,
    MiningLootTotalsUpdatedEvent,
)
from zml_game_bridge.domain.money import Mpec
from zml_game_bridge.inputs.chat.signals import ItemReceivedSignal
from zml_game_bridge.persistence.mining_loot import (
    MiningLootItemRow,
    MiningLootTotalRow,
    MiningLootWriteResult,
    RecordMiningLootItemCommand,
)
from zml_game_bridge.runtime.db_commands import DbCommand


class MiningLootRecorder:
    def __init__(
        self,
        db_command_executor: Callable[[DbCommand[Any]], Any],
        *,
        update_debounce_ms: int = 0,
    ) -> None:
        self._db_command_executor = db_command_executor
        self._update_debounce_ms = update_debounce_ms
        self._last_update_event_ts_ms: int | None = None

    def record_item(
        self,
        signal: ItemReceivedSignal,
        *,
        extraction_cost_mpec: Mpec | None,
        run_id: int | None,
        segment_id: str | None,
    ) -> MiningLootTotalsUpdatedEvent | None:
        result = cast(
            MiningLootWriteResult,
            self._db_command_executor(
                RecordMiningLootItemCommand(
                    event_dt=signal.event_dt,
                    item_name=signal.item_name,
                    qty=signal.qty,
                    value_mpec=signal.value_mpec,
                    raw=signal.raw,
                    extraction_cost_mpec=extraction_cost_mpec,
                    run_id=run_id,
                    segment_id=segment_id,
                )
            ),
        )
        updated_ts_ms = result.recent_item.created_ts_ms
        if not self._should_emit_update(updated_ts_ms):
            return None
        self._last_update_event_ts_ms = updated_ts_ms
        return MiningLootTotalsUpdatedEvent(
            updated_ts_ms=updated_ts_ms,
            run_id=run_id,
            segment_id=segment_id,
            recent_item=_item_snapshot(result.recent_item),
            run_total=_total_snapshot(result.run_total),
            segment_total=_total_snapshot(result.segment_total),
        )

    def _should_emit_update(self, updated_ts_ms: int) -> bool:
        if self._update_debounce_ms <= 0:
            return True
        if self._last_update_event_ts_ms is None:
            return True
        return updated_ts_ms - self._last_update_event_ts_ms >= self._update_debounce_ms


def _item_snapshot(row: MiningLootItemRow) -> MiningLootItemSnapshot:
    return MiningLootItemSnapshot(
        event_id=row.event_id,
        created_ts_ms=row.created_ts_ms,
        event_dt=row.event_dt,
        run_id=row.run_id,
        segment_id=row.segment_id,
        item_name=row.item_name,
        qty=row.qty,
        value_mpec=row.value_mpec,
        extraction_cost_mpec=row.extraction_cost_mpec,
    )


def _total_snapshot(row: MiningLootTotalRow | None) -> MiningLootTotalSnapshot | None:
    if row is None:
        return None
    return MiningLootTotalSnapshot(
        scope=row.scope,
        run_id=row.run_id,
        segment_id=row.segment_id,
        item_name=row.item_name,
        qty=row.qty,
        value_mpec=row.value_mpec,
        extraction_cost_mpec=row.extraction_cost_mpec,
        event_count=row.event_count,
        first_seen_ts_ms=row.first_seen_ts_ms,
        last_seen_ts_ms=row.last_seen_ts_ms,
    )
