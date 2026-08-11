from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from zml_ocr_worker.calibration.compass import CompassLocator
from zml_ocr_worker.calibration.coordinates import (
    CompassCoordinateLayout,
    CompassCoordinateLayoutVariant,
)
from zml_ocr_worker.calibration.model import LocatedCompass
from zml_ocr_worker.calibration.recovery import CompassRecoveryPolicy
from zml_ocr_worker.pipelines.position.model import CoordinateRois
from zml_ocr_worker.pipelines.position.pipeline import PositionPipeline, PositionReadResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CompassCalibrationRuntimeConfig:
    search_interval_ms: int = 1000
    reacquire_delay_ms: int = 250


@dataclass(frozen=True, slots=True)
class CalibratedPositionStep:
    compass: LocatedCompass | None
    compass_roi: np.ndarray | None
    read: PositionReadResult
    reacquire_requested: bool = False


class CompassCalibrationRuntime:
    """Coordinate Compass location, line-layout recovery, and the existing position OCR.

    Calibration owns only geometry and recovery state. PositionPipeline remains the
    single owner of image preprocessing, OCR, parsing, sanity checks, and emission.
    """

    def __init__(
        self,
        *,
        position_pipeline: PositionPipeline,
        locator: CompassLocator | None = None,
        layout: CompassCoordinateLayout | None = None,
        config: CompassCalibrationRuntimeConfig | None = None,
    ) -> None:
        self._position_pipeline = position_pipeline
        self._locator = locator or CompassLocator()
        self._layout = layout or CompassCoordinateLayout()
        self._config = config or CompassCalibrationRuntimeConfig()
        self._compass: LocatedCompass | None = None
        self._variants: tuple[CompassCoordinateLayoutVariant, ...] = ()
        self._recovery: CompassRecoveryPolicy | None = None
        self._next_search_ts_ms = 0

    @property
    def compass(self) -> LocatedCompass | None:
        return self._compass

    @property
    def layout_index(self) -> int:
        return 0 if self._recovery is None else self._recovery.layout_index

    @property
    def active_rois(self) -> CoordinateRois | None:
        if self._recovery is None or not self._variants:
            return None
        index = self._recovery.layout_index
        if index < 0 or index >= len(self._variants):
            return None
        return self._variants[index].rois

    def invalidate(self, *, next_search_ts_ms: int = 0) -> None:
        self._compass = None
        self._variants = ()
        self._recovery = None
        self._next_search_ts_ms = max(0, next_search_ts_ms)

    def step(self, frame: np.ndarray, *, ts_ms: int) -> CalibratedPositionStep:
        if self._compass is None:
            if ts_ms < self._next_search_ts_ms:
                return _empty_step()
            self._next_search_ts_ms = ts_ms + max(1, self._config.search_interval_ms)
            if not self._locate(frame):
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

        recovery = self._recovery
        if recovery is None or not self._variants:
            self.invalidate(next_search_ts_ms=ts_ms + self._config.reacquire_delay_ms)
            return _empty_step(reacquire_requested=True)

        read = self._read_variant(compass_roi, ts_ms=ts_ms, index=recovery.layout_index)
        decision = recovery.observe(read_healthy=self._read_is_healthy(read))

        if decision.action == "use_layout":
            logger.info(
                "compass_coordinate_layout_shift layout=%s lon=%s lat=%s confidence=%s",
                decision.layout_index,
                read.longitude,
                read.latitude,
                _format_confidence(read.confidence),
            )
            # Once the hysteresis threshold is reached, retry the shifted line layout
            # on the same frame instead of waiting for another capture tick.
            read = self._read_variant(compass_roi, ts_ms=ts_ms, index=decision.layout_index)
            if self._read_is_healthy(read):
                recovery.observe(read_healthy=True)

        if decision.action == "relocate_compass":
            # Exhausting coordinate-line variants does not prove that the Compass moved.
            # First validate the already locked radar at its known center/radius. This is
            # much cheaper than another full-frame Hough search and prevents a bad OCR
            # crop streak from causing an endless locate -> fail -> locate loop.
            locked_score = self._locator.validate_locked(frame, compass)
            if self._locator.locked_is_valid(frame, compass):
                logger.info(
                    "compass_coordinate_recovery_kept_locked score=%.3f lon=%s lat=%s confidence=%s",
                    locked_score,
                    read.longitude,
                    read.latitude,
                    _format_confidence(read.confidence),
                )
                recovery.reset_after_relocation()
                return CalibratedPositionStep(
                    compass=compass,
                    compass_roi=compass_roi,
                    read=read,
                )

            logger.info(
                "compass_locked_geometry_invalid score=%.3f; requesting full reacquire",
                locked_score,
            )
            self.invalidate(next_search_ts_ms=ts_ms + self._config.reacquire_delay_ms)
            return CalibratedPositionStep(
                compass=compass,
                compass_roi=compass_roi,
                read=read,
                reacquire_requested=True,
            )

        return CalibratedPositionStep(
            compass=compass,
            compass_roi=compass_roi,
            read=read,
        )

    def _locate(self, frame: np.ndarray) -> bool:
        compass = self._locator.locate(frame)
        if compass is None:
            return False
        variants = self._layout.variants(compass)
        if not variants:
            return False

        self._compass = compass
        self._variants = variants
        self._recovery = CompassRecoveryPolicy(layout_count=len(variants))
        self._next_search_ts_ms = 0
        return True

    def _read_variant(
        self,
        compass_roi: np.ndarray,
        *,
        ts_ms: int,
        index: int,
    ) -> PositionReadResult:
        variant = self._variants[index]
        # There is exactly one Lon line and one Lat line per layout. MeanTextConf is
        # useful diagnostic data, but live testing shows it can be zero for correctly
        # parsed numeric-only reads, so it must not suppress emission or drive geometry
        # recovery by itself.
        return self._position_pipeline.read(
            compass_roi,
            ts_ms,
            rois=variant.rois,
        )

    @staticmethod
    def _read_is_healthy(read: PositionReadResult) -> bool:
        return read.valid


def _empty_step(*, reacquire_requested: bool = False) -> CalibratedPositionStep:
    return CalibratedPositionStep(
        compass=None,
        compass_roi=None,
        read=_empty_read(),
        reacquire_requested=reacquire_requested,
    )


def _empty_read() -> PositionReadResult:
    return PositionReadResult(longitude=None, latitude=None, position=None)


def _format_confidence(value: float | None) -> str:
    return "none" if value is None else f"{value:.3f}"
