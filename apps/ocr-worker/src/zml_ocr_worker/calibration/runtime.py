from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from zml_ocr_worker.calibration.compass import CompassLocator
from zml_ocr_worker.calibration.coordinates import (
    CompassCoordinateLayout,
    CompassCoordinateLayoutVariant,
)
from zml_ocr_worker.calibration.model import LocatedCompass
from zml_ocr_worker.calibration.recovery import CompassRecoveryPolicy
from zml_ocr_worker.pipelines.position.pipeline import PositionPipeline, PositionReadResult


@dataclass(frozen=True, slots=True)
class CalibratedPositionStep:
    compass: LocatedCompass | None
    compass_roi: np.ndarray | None
    read: PositionReadResult
    reacquire_requested: bool = False


class CompassCalibrationRuntime:
    """Coordinate Compass location, line-layout recovery, and the existing position OCR.

    Calibration owns only geometry and recovery state. PositionPipeline remains the
    single owner of image preprocessing, OCR, parsing, and sanity checks.
    """

    def __init__(
        self,
        *,
        position_pipeline: PositionPipeline,
        locator: CompassLocator | None = None,
        layout: CompassCoordinateLayout | None = None,
    ) -> None:
        self._position_pipeline = position_pipeline
        self._locator = locator or CompassLocator()
        self._layout = layout or CompassCoordinateLayout()
        self._compass: LocatedCompass | None = None
        self._variants: tuple[CompassCoordinateLayoutVariant, ...] = ()
        self._recovery: CompassRecoveryPolicy | None = None

    @property
    def compass(self) -> LocatedCompass | None:
        return self._compass

    @property
    def layout_index(self) -> int:
        return 0 if self._recovery is None else self._recovery.layout_index

    def invalidate(self) -> None:
        self._compass = None
        self._variants = ()
        self._recovery = None

    def step(self, frame: np.ndarray, *, ts_ms: int) -> CalibratedPositionStep:
        if self._compass is None and not self._locate(frame):
            return _empty_step()

        compass = self._compass
        if compass is None:
            return _empty_step()

        compass_roi = compass.rect.crop(frame)
        if compass_roi is None:
            self.invalidate()
            return CalibratedPositionStep(
                compass=None,
                compass_roi=None,
                read=_empty_read(),
                reacquire_requested=True,
            )

        recovery = self._recovery
        if recovery is None or not self._variants:
            self.invalidate()
            return _empty_step(reacquire_requested=True)

        read = self._read_variant(compass_roi, ts_ms=ts_ms, index=recovery.layout_index)
        decision = recovery.observe(read_healthy=read.valid)

        if decision.action == "use_layout":
            # Once the hysteresis threshold is reached, retry the shifted line layout
            # on the same frame instead of waiting for another capture tick.
            read = self._read_variant(compass_roi, ts_ms=ts_ms, index=decision.layout_index)
            if read.valid:
                recovery.observe(read_healthy=True)

        if decision.action == "relocate_compass":
            self.invalidate()
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
        return True

    def _read_variant(
        self,
        compass_roi: np.ndarray,
        *,
        ts_ms: int,
        index: int,
    ) -> PositionReadResult:
        variant = self._variants[index]
        return self._position_pipeline.read_candidates(
            compass_roi,
            ts_ms,
            variant.roi_candidates,
        )


def _empty_step(*, reacquire_requested: bool = False) -> CalibratedPositionStep:
    return CalibratedPositionStep(
        compass=None,
        compass_roi=None,
        read=_empty_read(),
        reacquire_requested=reacquire_requested,
    )


def _empty_read() -> PositionReadResult:
    return PositionReadResult(longitude=None, latitude=None, position=None)
