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
PlanetObserver = Callable[[str], None]
logger = logging.getLogger(__name__)


class PositionInputProcessor:
    def __init__(
        self,
        position_service: PositionTrackingService,
        *,
        clock_ms: ClockMs | None = None,
        planet_observer: PlanetObserver | None = None,
    ) -> None:
        self._position_service = position_service
        self._clock_ms = clock_ms or _now_ms
        self._planet_observer = planet_observer

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
        if decision.accepted and signal.position.planet_name and self._planet_observer is not None:
            self._planet_observer(signal.position.planet_name)
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
