from __future__ import annotations

import logging
import time
from collections.abc import Callable

from zml_backend.application.position.model import PositionSnapshot
from zml_backend.application.position.tracking import PositionTrackingService
from zml_backend.events.base import EventBase, SignalBase
from zml_backend.inputs.chat.signals import PlayerPosWaypointSignal
from zml_backend.runtime.runtime_commands import (
    RuntimeCommand,
    RuntimeCommandResult,
    UnsupportedRuntimeCommandError,
)

ClockMs = Callable[[], int]
logger = logging.getLogger(__name__)


class PositionInputProcessor:
    def __init__(
        self,
        position_service: PositionTrackingService,
        *,
        clock_ms: ClockMs | None = None,
    ) -> None:
        self._position_service = position_service
        self._clock_ms = clock_ms or _now_ms

    def process_signal(self, signal: SignalBase) -> tuple[EventBase, ...]:
        if not isinstance(signal, PlayerPosWaypointSignal):
            return ()

        received_ts_ms = self._clock_ms()
        decision = self._position_service.ingest_snapshot(
            PositionSnapshot(
                observed_ts_ms=received_ts_ms,
                received_ts_ms=received_ts_ms,
                position=signal.position,
                source="chat",
                confidence=1.0,
            )
        )
        logger.debug(
            "chat_position_signal_processed decision=%s event_dt=%s position=%s",
            decision.kind,
            signal.event_dt,
            signal.position,
        )
        return ()

    def process_command[T](self, command: RuntimeCommand[T]) -> RuntimeCommandResult[T]:
        raise UnsupportedRuntimeCommandError(type(command).__name__)


def _now_ms() -> int:
    return time.time_ns() // 1_000_000
