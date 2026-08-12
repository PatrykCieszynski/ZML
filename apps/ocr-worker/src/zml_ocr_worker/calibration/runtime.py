from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from zml_ocr_worker.calibration.compass import CompassLocator
from zml_ocr_worker.calibration.coordinate_ocr import (
    CoordinateCalibration,
    CoordinateTextCalibrator,
)
from zml_ocr_worker.calibration.coordinates import CompassCoordinateLayout
from zml_ocr_worker.calibration.model import LocatedCompass
from zml_ocr_worker.calibration.multiframe_compass import MultiFrameCompassLocator
from zml_ocr_worker.calibration.persistence import (
    CompassCalibrationStore,
    PersistedCompassCalibration,
)
from zml_ocr_worker.capture.model import RoiRect
from zml_ocr_worker.pipelines.position.model import CoordinateRois
from zml_ocr_worker.pipelines.position.pipeline import PositionPipeline, PositionReadResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CompassCalibrationRuntimeConfig:
    search_interval_ms: int = 1000
    acquisition_sample_interval_ms: int = 100
    reacquire_delay_ms: int = 250
    locked_validation_interval_ms: int = 1000
    coordinate_recalibration_cooldown_ms: int = 2000
    consecutive_failures_before_recalibrate: int = 5
    verified_reads_before_persist: int = 10


@dataclass(frozen=True, slots=True)
class CalibratedPositionStep:
    compass: LocatedCompass | None
    compass_roi: np.ndarray | None
    read: PositionReadResult
    reacquire_requested: bool = False


class CompassCalibrationRuntime:
    """Keep Compass geometry and coordinate OCR calibration as separate states.

    The expensive Compass locator owns only radar geometry. A separate occasional
    text OCR finds the current Lon:/Lat: value boxes. Normal runtime then reuses
    those boxes for two small digits-only OCR calls. Coordinate OCR failures never
    invalidate a still-valid Compass.
    """

    def __init__(
        self,
        *,
        position_pipeline: PositionPipeline,
        locator: CompassLocator | None = None,
        layout: CompassCoordinateLayout | None = None,
        coordinate_calibrator: CoordinateTextCalibrator | None = None,
        state_store: CompassCalibrationStore | None = None,
        config: CompassCalibrationRuntimeConfig | None = None,
    ) -> None:
        self._position_pipeline = position_pipeline
        self._locator = locator or MultiFrameCompassLocator()
        self._layout = layout or CompassCoordinateLayout()
        self._coordinate_calibrator = coordinate_calibrator or CoordinateTextCalibrator()
        self._state_store = state_store
        self._config = config or CompassCalibrationRuntimeConfig()

        self._compass: LocatedCompass | None = None
        self._search_rois: CoordinateRois | None = None
        self._coordinate_rois: CoordinateRois | None = None
        self._expected_digit_counts: tuple[int, int] | None = None
        self._pending_digit_counts: tuple[int, int] | None = None
        self._pending_digit_count_streak = 0
        self._coordinate_failure_streak = 0
        self._frame_size: tuple[int, int] | None = None
        self._persisted_restore_attempted = False
        self._calibration_persisted = False
        self._verified_read_streak = 0

        self._next_search_ts_ms = 0
        self._next_locked_validation_ts_ms = 0
        self._next_coordinate_calibration_ts_ms = 0

    @property
    def compass(self) -> LocatedCompass | None:
        return self._compass

    @property
    def layout_index(self) -> int:
        return 0

    @property
    def active_rois(self) -> CoordinateRois | None:
        return self._coordinate_rois

    def close(self) -> None:
        self._coordinate_calibrator.close()

    def invalidate(self, *, next_search_ts_ms: int = 0) -> None:
        self._compass = None
        self._search_rois = None
        self._coordinate_rois = None
        self._expected_digit_counts = None
        self._frame_size = None
        self._calibration_persisted = False
        self._verified_read_streak = 0
        self._reset_coordinate_health()
        self._next_search_ts_ms = max(0, next_search_ts_ms)
        self._next_locked_validation_ts_ms = 0
        self._next_coordinate_calibration_ts_ms = 0

    def step(self, frame: np.ndarray, *, ts_ms: int) -> CalibratedPositionStep:
        if self._compass is None and not self._persisted_restore_attempted:
            self._persisted_restore_attempted = True
            self._try_restore_persisted(frame)

        if self._compass is None:
            if ts_ms < self._next_search_ts_ms:
                return _empty_step()
            if not self._locate(frame):
                acquisition_in_progress = bool(getattr(self._locator, "acquiring", False))
                delay_ms = (
                    self._config.acquisition_sample_interval_ms
                    if acquisition_in_progress
                    else self._config.search_interval_ms
                )
                self._next_search_ts_ms = ts_ms + max(1, delay_ms)
                return _empty_step()

        compass = self._compass
        if compass is None:
            return _empty_step()

        compass_roi = compass.rect.crop(frame)
        if compass_roi is None:
            self.invalidate(next_search_ts_ms=ts_ms + self._config.reacquire_delay_ms)
            return CalibratedPositionStep(
                compass=None,
                compass_roi=None,
                read=_empty_read(),
                reacquire_requested=True,
            )

        if ts_ms >= self._next_locked_validation_ts_ms:
            self._next_locked_validation_ts_ms = ts_ms + max(
                1, self._config.locked_validation_interval_ms
            )
            if not self._locator.locked_is_valid(frame, compass):
                score = self._locator.validate_locked(frame, compass)
                logger.info(
                    "compass_locked_geometry_invalid score=%.3f; requesting full reacquire",
                    score,
                )
                self.invalidate(next_search_ts_ms=ts_ms + self._config.reacquire_delay_ms)
                return CalibratedPositionStep(
                    compass=compass,
                    compass_roi=compass_roi,
                    read=_empty_read(),
                    reacquire_requested=True,
                )

        if self._coordinate_rois is None:
            if ts_ms >= self._next_coordinate_calibration_ts_ms:
                self._try_coordinate_calibration(compass_roi, ts_ms=ts_ms, reason="initial")
            if self._coordinate_rois is None:
                return CalibratedPositionStep(
                    compass=compass,
                    compass_roi=compass_roi,
                    read=_empty_read(),
                )

        read = self._read_fast(compass_roi, ts_ms=ts_ms)
        if read.valid:
            if self._expected_digit_counts is None:
                self._remember_digit_counts(read)
                self._reset_coordinate_health()
                read = self._position_pipeline.emit_read(read, ts_ms=ts_ms)
                self._record_verified_read()
                return CalibratedPositionStep(
                    compass=compass,
                    compass_roi=compass_roi,
                    read=read,
                )

            if self._digit_count_changed(read):
                self._verified_read_streak = 0
                changed_counts = _digit_counts(read)
                self._record_digit_count_mismatch(changed_counts)
                if self._pending_digit_count_streak == 1:
                    logger.info(
                        "coordinate_digit_count_suspect lon=%s lat=%s expected=%s observed=%s; holding read",
                        read.longitude,
                        read.latitude,
                        self._expected_digit_counts,
                        changed_counts,
                    )
                return self._recover_unhealthy_read(
                    compass=compass,
                    compass_roi=compass_roi,
                    read=read,
                    ts_ms=ts_ms,
                    reason="digit_count_changed",
                )

            self._reset_coordinate_health()
            read = self._position_pipeline.emit_read(read, ts_ms=ts_ms)
            self._record_verified_read()
            return CalibratedPositionStep(
                compass=compass,
                compass_roi=compass_roi,
                read=read,
            )

        self._verified_read_streak = 0
        self._pending_digit_counts = None
        self._pending_digit_count_streak = 0
        return self._recover_unhealthy_read(
            compass=compass,
            compass_roi=compass_roi,
            read=read,
            ts_ms=ts_ms,
            reason="fast_ocr_failures",
        )

    def _recover_unhealthy_read(
        self,
        *,
        compass: LocatedCompass,
        compass_roi: np.ndarray,
        read: PositionReadResult,
        ts_ms: int,
        reason: str,
    ) -> CalibratedPositionStep:
        self._verified_read_streak = 0
        self._coordinate_failure_streak += 1
        threshold = max(1, self._config.consecutive_failures_before_recalibrate)
        if (
            self._coordinate_failure_streak >= threshold
            and ts_ms >= self._next_coordinate_calibration_ts_ms
            and self._try_coordinate_calibration(
                compass_roi,
                ts_ms=ts_ms,
                reason=reason,
            )
        ):
            fresh = self._read_fast(compass_roi, ts_ms=ts_ms)
            if fresh.valid:
                fresh_counts = _digit_counts(fresh)
                expected = self._expected_digit_counts
                if reason == "digit_count_changed" and expected is not None:
                    pending = self._pending_digit_counts
                    if (
                        pending is not None
                        and self._pending_digit_count_streak >= threshold
                        and fresh_counts == pending
                    ):
                        logger.info(
                            "coordinate_digit_count_change_confirmed expected=%s observed=%s",
                            expected,
                            fresh_counts,
                        )
                        self._remember_digit_counts(fresh)
                        self._reset_coordinate_health()
                        fresh = self._position_pipeline.emit_read(fresh, ts_ms=ts_ms)
                        self._record_verified_read()
                        read = fresh
                    elif fresh_counts == expected:
                        self._reset_coordinate_health()
                        fresh = self._position_pipeline.emit_read(fresh, ts_ms=ts_ms)
                        self._record_verified_read()
                        read = fresh
                else:
                    self._remember_digit_counts(fresh)
                    self._reset_coordinate_health()
                    fresh = self._position_pipeline.emit_read(fresh, ts_ms=ts_ms)
                    self._record_verified_read()
                    read = fresh

        return CalibratedPositionStep(
            compass=compass,
            compass_roi=compass_roi,
            read=read,
        )

    def _try_restore_persisted(self, frame: np.ndarray) -> bool:
        store = self._state_store
        if store is None:
            return False
        state = store.load()
        if state is None:
            return False

        frame_height = int(frame.shape[0])
        frame_width = int(frame.shape[1])
        if state.frame_width != frame_width or state.frame_height != frame_height:
            logger.info(
                "compass_calibration_state_ignored reason=frame_size stored=%sx%s current=%sx%s",
                state.frame_width,
                state.frame_height,
                frame_width,
                frame_height,
            )
            return False

        compass_roi = state.compass.rect.crop(frame)
        if (
            compass_roi is None
            or state.rois.lon.crop(compass_roi) is None
            or state.rois.lat.crop(compass_roi) is None
        ):
            logger.info("compass_calibration_state_ignored reason=invalid_rois")
            return False

        variants = self._layout.variants(state.compass)
        if not variants:
            logger.info("compass_calibration_state_ignored reason=no_layout")
            return False

        # A locked locator intentionally tolerates one failed validation. Require
        # two successful checks here so stale persisted geometry cannot consume
        # that grace period during startup.
        if not self._locator.locked_is_valid(
            frame, state.compass
        ) or not self._locator.locked_is_valid(frame, state.compass):
            logger.info("compass_calibration_state_ignored reason=locked_validation")
            return False

        self._compass = state.compass
        self._search_rois = variants[0].rois
        self._coordinate_rois = state.rois
        self._expected_digit_counts = None
        self._frame_size = (frame_width, frame_height)
        self._calibration_persisted = True
        self._verified_read_streak = 0
        self._reset_coordinate_health()
        self._next_search_ts_ms = 0
        self._next_locked_validation_ts_ms = 0
        self._next_coordinate_calibration_ts_ms = 0
        logger.info(
            "compass_calibration_state_restored rect=%s lon_roi=%s lat_roi=%s",
            _rect_tuple(state.compass.rect),
            _rect_tuple(state.rois.lon),
            _rect_tuple(state.rois.lat),
        )
        return True

    def _locate(self, frame: np.ndarray) -> bool:
        compass = self._locator.locate(frame)
        if compass is None:
            return False
        variants = self._layout.variants(compass)
        if not variants:
            return False

        self._compass = compass
        self._search_rois = variants[0].rois
        self._coordinate_rois = None
        self._expected_digit_counts = None
        self._frame_size = (int(frame.shape[1]), int(frame.shape[0]))
        self._calibration_persisted = False
        self._verified_read_streak = 0
        self._reset_coordinate_health()
        self._next_search_ts_ms = 0
        self._next_locked_validation_ts_ms = 0
        self._next_coordinate_calibration_ts_ms = 0
        return True

    def _try_coordinate_calibration(
        self,
        compass_roi: np.ndarray,
        *,
        ts_ms: int,
        reason: str,
    ) -> bool:
        search_rois = self._search_rois
        if search_rois is None:
            return False
        self._next_coordinate_calibration_ts_ms = ts_ms + max(
            1, self._config.coordinate_recalibration_cooldown_ms
        )
        try:
            calibration = self._coordinate_calibrator.calibrate(
                compass_roi,
                search_rois=search_rois,
            )
        except Exception:
            logger.warning(
                "coordinate_text_calibration_failed reason=%s error=exception",
                reason,
                exc_info=True,
            )
            return False
        if calibration is None:
            logger.info("coordinate_text_calibration_failed reason=%s", reason)
            return False

        self._apply_coordinate_calibration(calibration, reason=reason)
        return True

    def _apply_coordinate_calibration(
        self,
        calibration: CoordinateCalibration,
        *,
        reason: str,
    ) -> None:
        self._coordinate_rois = calibration.rois
        self._coordinate_failure_streak = 0
        self._calibration_persisted = False
        self._verified_read_streak = 0
        lon = calibration.rois.lon
        lat = calibration.rois.lat
        logger.info(
            "coordinate_text_calibrated reason=%s lon_roi=%s lat_roi=%s",
            reason,
            (lon.x1, lon.y1, lon.x2, lon.y2),
            (lat.x1, lat.y1, lat.x2, lat.y2),
        )

    def _record_verified_read(self) -> None:
        if self._calibration_persisted:
            return
        store = self._state_store
        compass = self._compass
        rois = self._coordinate_rois
        frame_size = self._frame_size
        if store is None or compass is None or rois is None or frame_size is None:
            return

        self._verified_read_streak += 1
        threshold = max(1, self._config.verified_reads_before_persist)
        if self._verified_read_streak < threshold:
            return

        frame_width, frame_height = frame_size
        state = PersistedCompassCalibration(
            frame_width=frame_width,
            frame_height=frame_height,
            compass=compass,
            rois=rois,
        )
        if store.save(state):
            self._calibration_persisted = True
            logger.info(
                "compass_calibration_verified reads=%s rect=%s",
                self._verified_read_streak,
                _rect_tuple(compass.rect),
            )

    def _read_fast(self, compass_roi: np.ndarray, *, ts_ms: int) -> PositionReadResult:
        rois = self._coordinate_rois
        if rois is None:
            return _empty_read()
        return self._position_pipeline.read(
            compass_roi,
            ts_ms,
            rois=rois,
            emit=False,
        )

    def _remember_digit_counts(self, read: PositionReadResult) -> None:
        counts = _digit_counts(read)
        if counts is None:
            return
        self._expected_digit_counts = counts
        logger.info("coordinate_digit_rois_verified digits=%s", counts)

    def _digit_count_changed(self, read: PositionReadResult) -> bool:
        expected = self._expected_digit_counts
        counts = _digit_counts(read)
        return expected is not None and counts is not None and counts != expected

    def _record_digit_count_mismatch(self, counts: tuple[int, int] | None) -> None:
        if counts is None:
            self._pending_digit_counts = None
            self._pending_digit_count_streak = 0
            return
        if counts == self._pending_digit_counts:
            self._pending_digit_count_streak += 1
            return
        self._pending_digit_counts = counts
        self._pending_digit_count_streak = 1

    def _reset_coordinate_health(self) -> None:
        self._coordinate_failure_streak = 0
        self._pending_digit_counts = None
        self._pending_digit_count_streak = 0


def _digit_counts(read: PositionReadResult) -> tuple[int, int] | None:
    if not read.valid or read.longitude is None or read.latitude is None:
        return None
    return (
        len(str(abs(read.longitude))),
        len(str(abs(read.latitude))),
    )


def _rect_tuple(rect: RoiRect) -> tuple[int, int, int, int]:
    return rect.x1, rect.y1, rect.x2, rect.y2


def _empty_step(*, reacquire_requested: bool = False) -> CalibratedPositionStep:
    return CalibratedPositionStep(
        compass=None,
        compass_roi=None,
        read=_empty_read(),
        reacquire_requested=reacquire_requested,
    )


def _empty_read() -> PositionReadResult:
    return PositionReadResult(longitude=None, latitude=None, position=None)
