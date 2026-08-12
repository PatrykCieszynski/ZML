from __future__ import annotations

from dataclasses import dataclass
from math import hypot

from zml_backend.application.position.model import (
    PositionDecision,
    PositionSnapshot,
    PositionTrackingConfig,
)


@dataclass(frozen=True, slots=True)
class _RelocationCandidate:
    first_snapshot: PositionSnapshot
    latest_snapshot: PositionSnapshot
    center_x: float
    center_y: float
    samples: int


class PositionOutlierPolicy:
    def __init__(self, config: PositionTrackingConfig | None = None) -> None:
        self._config = config or PositionTrackingConfig()
        self._candidate: _RelocationCandidate | None = None

    def evaluate(
        self,
        snapshot: PositionSnapshot,
        *,
        stable_snapshot: PositionSnapshot | None,
    ) -> PositionDecision:
        if not self._config.outlier_filter_enabled:
            self._candidate = None
            return PositionDecision(kind="accepted", snapshot=snapshot, reason="filter_disabled")

        if stable_snapshot is None:
            self._candidate = None
            return PositionDecision(kind="accepted", snapshot=snapshot, reason="initial")

        if snapshot.observed_ts_ms <= stable_snapshot.observed_ts_ms:
            return PositionDecision(
                kind="stale_rejected",
                snapshot=None,
                reason="older_than_stable",
                stable_snapshot=stable_snapshot,
            )

        if snapshot.source != "ocr" or _planet_changed(stable_snapshot, snapshot):
            self._candidate = None
            return PositionDecision(
                kind="trusted_reset",
                snapshot=snapshot,
                reason="trusted_source_or_planet_changed",
                stable_snapshot=stable_snapshot,
            )

        distance_m = _distance_xy(stable_snapshot, snapshot)
        allowed_m = self._allowed_distance_m(stable_snapshot, snapshot)
        if distance_m <= allowed_m:
            self._candidate = None
            return PositionDecision(
                kind="accepted",
                snapshot=snapshot,
                reason="within_movement_threshold",
                stable_snapshot=stable_snapshot,
                distance_m=distance_m,
                allowed_m=allowed_m,
            )

        return self._handle_outlier(
            snapshot,
            stable_snapshot=stable_snapshot,
            distance_m=distance_m,
            allowed_m=allowed_m,
        )

    def _handle_outlier(
        self,
        snapshot: PositionSnapshot,
        *,
        stable_snapshot: PositionSnapshot,
        distance_m: float,
        allowed_m: float,
    ) -> PositionDecision:
        candidate = self._candidate
        if candidate is None or _candidate_distance_m(candidate, snapshot) > (
            self._config.relocation_cluster_radius_m
        ):
            candidate = _RelocationCandidate(
                first_snapshot=snapshot,
                latest_snapshot=snapshot,
                center_x=float(snapshot.position.x),
                center_y=float(snapshot.position.y),
                samples=1,
            )
        else:
            samples = candidate.samples + 1
            candidate = _RelocationCandidate(
                first_snapshot=candidate.first_snapshot,
                latest_snapshot=snapshot,
                center_x=(candidate.center_x * candidate.samples + snapshot.position.x) / samples,
                center_y=(candidate.center_y * candidate.samples + snapshot.position.y) / samples,
                samples=samples,
            )

        self._candidate = candidate
        candidate_age_s = max(
            0.0,
            (snapshot.observed_ts_ms - candidate.first_snapshot.observed_ts_ms) / 1000.0,
        )

        if (
            candidate.samples >= self._config.relocation_min_samples
            and candidate_age_s >= self._config.relocation_confirm_s
        ):
            self._candidate = None
            return PositionDecision(
                kind="relocation_accepted",
                snapshot=snapshot,
                reason="relocation_confirmed",
                stable_snapshot=stable_snapshot,
                distance_m=distance_m,
                allowed_m=allowed_m,
                candidate_samples=candidate.samples,
                candidate_age_s=candidate_age_s,
            )

        return PositionDecision(
            kind="suspect_relocation" if candidate.samples > 1 else "rejected_outlier",
            snapshot=None,
            reason="outside_movement_threshold",
            stable_snapshot=stable_snapshot,
            distance_m=distance_m,
            allowed_m=allowed_m,
            candidate_samples=candidate.samples,
            candidate_age_s=candidate_age_s,
        )

    def _allowed_distance_m(self, previous: PositionSnapshot, current: PositionSnapshot) -> float:
        elapsed_s = max(0.0, (current.observed_ts_ms - previous.observed_ts_ms) / 1000.0)
        normal_allowed_m = self._config.max_jump_m + self._config.max_speed_mps * elapsed_s
        confidence = current.confidence
        if confidence is None or confidence >= self._config.low_confidence_threshold:
            return normal_allowed_m

        # Low confidence is not an automatic rejection. It only tightens the distance
        # envelope so a nearby, physically plausible reading still passes, while a
        # suspicious jump is routed through the existing relocation confirmation flow.
        low_confidence_cap_m = max(0.0, self._config.low_confidence_max_distance_m)
        return min(normal_allowed_m, low_confidence_cap_m)


def _planet_changed(previous: PositionSnapshot, current: PositionSnapshot) -> bool:
    previous_name = previous.position.planet_name
    current_name = current.position.planet_name
    return bool(previous_name and current_name and previous_name != current_name)


def _distance_xy(left: PositionSnapshot, right: PositionSnapshot) -> float:
    return hypot(right.position.x - left.position.x, right.position.y - left.position.y)


def _candidate_distance_m(candidate: _RelocationCandidate, snapshot: PositionSnapshot) -> float:
    return hypot(snapshot.position.x - candidate.center_x, snapshot.position.y - candidate.center_y)
