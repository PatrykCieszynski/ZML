from __future__ import annotations

import logging
from collections.abc import Callable
from threading import Lock

from zml_game_bridge.application.position.model import (
    PositionDecision,
    PositionSnapshot,
    PositionTrackingConfig,
)
from zml_game_bridge.application.position.outlier_policy import PositionOutlierPolicy
from zml_game_bridge.domain.position import WorldPos

PositionPublisher = Callable[[PositionSnapshot], None]
logger = logging.getLogger(__name__)


class PositionTrackingService:
    """
    Owns volatile position state and publishes accepted position updates.

    Position updates are high-frequency and are not part of the durable event
    store. This service is the application-level boundary between position
    inputs and consumers such as the map, mining coordinator, and claim lifecycle.
    """

    def __init__(
        self,
        *,
        publisher: PositionPublisher | None = None,
        config: PositionTrackingConfig | None = None,
        outlier_policy: PositionOutlierPolicy | None = None,
    ) -> None:
        self._config = config or PositionTrackingConfig()
        self._lock = Lock()
        self._latest: PositionSnapshot | None = None
        self._history: list[PositionSnapshot] = []
        self._publisher = publisher
        self._outlier_policy = outlier_policy or PositionOutlierPolicy(self._config)

    def set_publisher(self, publisher: PositionPublisher | None) -> None:
        with self._lock:
            self._publisher = publisher
            latest = self._latest

        if publisher is not None and latest is not None:
            publisher(latest)

    def ingest_snapshot(self, snapshot: PositionSnapshot) -> PositionDecision:
        with self._lock:
            decision = self._outlier_policy.evaluate(
                snapshot,
                stable_snapshot=self._latest,
            )
            if not decision.accepted:
                publisher = None
            else:
                assert decision.snapshot is not None
                self._latest = decision.snapshot
                self._append_history(decision.snapshot)
                publisher = self._publisher

        self._log_decision(decision)
        if publisher is not None and decision.snapshot is not None:
            publisher(decision.snapshot)

        return decision

    def get_latest(self) -> PositionSnapshot | None:
        with self._lock:
            return self._latest

    def get_history(self) -> tuple[PositionSnapshot, ...]:
        with self._lock:
            return tuple(self._history)

    def get_latest_world_pos(self) -> WorldPos | None:
        latest = self.get_latest()
        return latest.position if latest is not None else None

    def _append_history(self, snapshot: PositionSnapshot) -> None:
        cutoff_ts_ms = snapshot.observed_ts_ms - int(self._config.history_window_s * 1000)
        max_samples = max(1, self._config.history_max_samples)
        self._history.append(snapshot)
        self._history = [item for item in self._history if item.observed_ts_ms >= cutoff_ts_ms][
            -max_samples:
        ]

    def _log_decision(self, decision: PositionDecision) -> None:
        if decision.kind == "accepted":
            return
        logger.debug(
            "position_decision kind=%s reason=%s distance_m=%s allowed_m=%s "
            "candidate_samples=%s candidate_age_s=%s stable=%s snapshot=%s",
            decision.kind,
            decision.reason,
            _format_float(decision.distance_m),
            _format_float(decision.allowed_m),
            decision.candidate_samples,
            _format_float(decision.candidate_age_s),
            None if decision.stable_snapshot is None else decision.stable_snapshot.position,
            None if decision.snapshot is None else decision.snapshot.position,
        )


def _format_float(value: float | None) -> str | None:
    return None if value is None else f"{value:.2f}"
