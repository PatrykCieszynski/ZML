from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from zml_game_bridge.domain.mining import MiningMode
from zml_game_bridge.inputs.ocr.pipelines.mining_finder.model import (
    FinderFeatures,
    FinderStatusKind,
    MiningFinderSignal,
)
from zml_game_bridge.inputs.ocr.pipelines.mining_finder.vision import (
    FinderFeatureDetector,
    VisionFinderFeatureDetector,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MiningFinderPipelineConfig:
    probe_cooldown_ms: int = 900
    mode_stable_frames: int = 2
    units_stable_frames: int = 2
    invalid_mode_grace_ms: int = 2_000
    debug_logging: bool = False


class FinderFrameObserver(Protocol):
    def record_frame(
        self,
        finder_roi: np.ndarray,
        *,
        ts_ms: int,
        features: FinderFeatures,
        signals: list[MiningFinderSignal],
    ) -> None: ...


class MiningFinderPipeline:
    def __init__(
        self,
        *,
        detector: FinderFeatureDetector | None = None,
        cfg: MiningFinderPipelineConfig | None = None,
        frame_observer: FinderFrameObserver | None = None,
    ) -> None:
        self._detector = detector or VisionFinderFeatureDetector()
        self._cfg = cfg or MiningFinderPipelineConfig()
        self._frame_observer = frame_observer

        self._last_status_kind: FinderStatusKind | None = None
        self._last_probe_ts_ms: int | None = None

        self._stable_modes_mask: int | None = None
        self._pending_modes_mask: int | None = None
        self._pending_modes_frames = 0
        self._last_valid_modes_mask: int | None = None
        self._last_valid_modes_ts_ms: int | None = None

        self._stable_units: tuple[int | None, int | None] | None = None
        self._pending_units: tuple[int | None, int | None] | None = None
        self._pending_units_frames = 0
        self._found_hint_emitted = False
        self._no_resources_emitted = False

    def close(self) -> None:
        self._detector.close()

    def step(self, finder_roi: np.ndarray, ts_ms: int) -> list[MiningFinderSignal]:
        features = self._detector.detect(finder_roi)
        signals: list[MiningFinderSignal] = []

        if self._probe_started(features.status_kind, ts_ms):
            signals.append(
                MiningFinderSignal(
                    ts_ms=ts_ms,
                    kind="probe_fired",
                    modes_mask=self._effective_probe_modes(ts_ms),
                    probes_per_drop=features.probes_per_drop,
                    ammo_per_drop=features.ammo_per_drop,
                    raw_text=features.raw_status_text,
                    debug=features.debug,
                )
            )

        mode_signal = self._handle_modes(
            _modes_for_update(features, self._last_status_kind),
            ts_ms,
            features.debug,
        )
        if mode_signal is not None:
            signals.append(mode_signal)

        units_signal = self._handle_units(features, ts_ms)
        if units_signal is not None:
            signals.append(units_signal)

        hit_signal = self._handle_hit_hint(features, ts_ms)
        if hit_signal is not None:
            signals.append(hit_signal)

        no_resources_signal = self._handle_no_resources(features, ts_ms)
        if no_resources_signal is not None:
            signals.append(no_resources_signal)

        self._log_debug_changes(features, signals, ts_ms)
        if self._frame_observer is not None:
            self._frame_observer.record_frame(
                finder_roi,
                ts_ms=ts_ms,
                features=features,
                signals=signals,
            )
        self._last_status_kind = features.status_kind
        return signals

    def _probe_started(self, status_kind: FinderStatusKind | None, ts_ms: int) -> bool:
        if status_kind != "sending_probe" or self._last_status_kind == "sending_probe":
            return False
        if (
            self._last_probe_ts_ms is not None
            and ts_ms - self._last_probe_ts_ms < self._cfg.probe_cooldown_ms
        ):
            return False
        self._last_probe_ts_ms = ts_ms
        return True

    def _effective_probe_modes(self, ts_ms: int) -> int | None:
        if self._stable_modes_mask not in (None, int(MiningMode.NONE)):
            return self._stable_modes_mask

        if self._last_valid_modes_mask is None or self._last_valid_modes_ts_ms is None:
            return self._stable_modes_mask
        if ts_ms - self._last_valid_modes_ts_ms <= self._cfg.invalid_mode_grace_ms:
            return self._last_valid_modes_mask
        return self._stable_modes_mask

    def _handle_modes(
        self,
        modes_mask: int | None,
        ts_ms: int,
        debug: Mapping[str, float],
    ) -> MiningFinderSignal | None:
        if modes_mask is None:
            return None

        if modes_mask != self._pending_modes_mask:
            self._pending_modes_mask = modes_mask
            self._pending_modes_frames = 1
            return None

        self._pending_modes_frames += 1
        if self._pending_modes_frames < self._cfg.mode_stable_frames:
            return None

        if modes_mask == self._stable_modes_mask:
            return None

        previous = self._stable_modes_mask
        self._stable_modes_mask = modes_mask

        if modes_mask != int(MiningMode.NONE):
            self._last_valid_modes_mask = modes_mask
            self._last_valid_modes_ts_ms = ts_ms
            return MiningFinderSignal(
                ts_ms=ts_ms,
                kind="finder_modes_changed",
                modes_mask=modes_mask,
                previous_modes_mask=previous,
                debug=debug,
            )

        return MiningFinderSignal(
            ts_ms=ts_ms,
            kind="finder_mode_invalidated",
            modes_mask=modes_mask,
            previous_modes_mask=previous,
            debug=debug,
        )

    def _handle_units(self, features: FinderFeatures, ts_ms: int) -> MiningFinderSignal | None:
        units = (features.probes_per_drop, features.ammo_per_drop)
        if units == (None, None):
            return None

        if units != self._pending_units:
            self._pending_units = units
            self._pending_units_frames = 1
            return None

        self._pending_units_frames += 1
        if self._pending_units_frames < self._cfg.units_stable_frames:
            return None

        if units == self._stable_units:
            return None

        self._stable_units = units
        return MiningFinderSignal(
            ts_ms=ts_ms,
            kind="finder_units_changed",
            probes_per_drop=features.probes_per_drop,
            ammo_per_drop=features.ammo_per_drop,
            raw_text=features.raw_units_text,
        )

    def _handle_hit_hint(self, features: FinderFeatures, ts_ms: int) -> MiningFinderSignal | None:
        if features.status_kind != "found":
            if features.status_kind is not None:
                self._found_hint_emitted = False
            return None
        if self._found_hint_emitted:
            return None
        if (
            features.hit_size_label is None
            or features.hit_size_index is None
            or features.resource_name is None
        ):
            return None

        self._found_hint_emitted = True
        return MiningFinderSignal(
            ts_ms=ts_ms,
            kind="finder_hit_hint",
            hit_size_label=features.hit_size_label,
            hit_size_index=features.hit_size_index,
            resource_name=features.resource_name,
            range_m=features.range_m,
            depth_m=features.depth_m,
            raw_text=features.raw_status_text,
            raw_details_text=features.raw_details_text,
        )

    def _handle_no_resources(
        self,
        features: FinderFeatures,
        ts_ms: int,
    ) -> MiningFinderSignal | None:
        if features.status_kind != "no_resources":
            if features.status_kind is not None:
                self._no_resources_emitted = False
            return None
        if self._no_resources_emitted:
            return None

        self._no_resources_emitted = True
        return MiningFinderSignal(
            ts_ms=ts_ms,
            kind="finder_no_resources",
            raw_text=features.raw_status_text,
        )

    def _log_debug_changes(
        self,
        features: FinderFeatures,
        signals: list[MiningFinderSignal],
        ts_ms: int,
    ) -> None:
        if not self._cfg.debug_logging:
            return

        if features.status_kind != self._last_status_kind:
            logger.debug(
                "finder_status_changed ts=%s previous=%s current=%s modes=%s units=(probes=%s ammo=%s) "
                "radar=%s raw_status=%r raw_details=%r",
                ts_ms,
                self._last_status_kind,
                features.status_kind,
                features.modes_mask,
                features.probes_per_drop,
                features.ammo_per_drop,
                features.radar_signal_active,
                features.raw_status_text,
                features.raw_details_text,
            )

        for signal in signals:
            logger.debug(
                "finder_signal_emitted ts=%s kind=%s modes=%s units=(probes=%s ammo=%s) "
                "resource=%r size=%r range_m=%s depth_m=%s raw=%r",
                signal.ts_ms,
                signal.kind,
                signal.modes_mask,
                signal.probes_per_drop,
                signal.ammo_per_drop,
                signal.resource_name,
                _format_size(signal),
                signal.range_m,
                signal.depth_m,
                signal.raw_text,
            )


def _format_size(signal: MiningFinderSignal) -> str | None:
    if signal.hit_size_label is None or signal.hit_size_index is None:
        return None
    return f"{signal.hit_size_label} ({signal.hit_size_index})"


def _modes_for_update(
    features: FinderFeatures,
    last_status_kind: FinderStatusKind | None,
) -> int | None:
    if features.status_kind == "found":
        return None
    if features.status_kind is None and last_status_kind == "found":
        return None
    return features.modes_mask
