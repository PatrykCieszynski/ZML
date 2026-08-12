from __future__ import annotations

from collections import deque

import numpy as np

from zml_ocr_worker.calibration.coordinate_ocr import CoordinateCalibration
from zml_ocr_worker.calibration.model import LocatedCompass
from zml_ocr_worker.calibration.runtime import (
    CompassCalibrationRuntime,
    CompassCalibrationRuntimeConfig,
)
from zml_ocr_worker.capture.model import RoiRect
from zml_ocr_worker.pipelines.position.model import CoordinateRois
from zml_ocr_worker.pipelines.position.pipeline import PositionReadResult


class _FakeLocator:
    def __init__(self, compass: LocatedCompass, *, locked_valid: bool = True) -> None:
        self._compass = compass
        self._locked_valid = locked_valid
        self.locate_calls = 0

    def locate(self, frame: np.ndarray) -> LocatedCompass | None:
        self.locate_calls += 1
        return self._compass

    def locked_is_valid(self, frame: np.ndarray, compass: LocatedCompass) -> bool:
        return self._locked_valid

    def validate_locked(self, frame: np.ndarray, compass: LocatedCompass) -> float:
        return 1.0 if self._locked_valid else 0.0


class _FakeCalibrator:
    def __init__(self, *responses: CoordinateCalibration | None) -> None:
        self._responses = deque(responses)
        self.calls = 0

    def calibrate(
        self,
        compass_roi: np.ndarray,
        *,
        search_rois: CoordinateRois,
    ) -> CoordinateCalibration | None:
        self.calls += 1
        if not self._responses:
            return None
        return self._responses.popleft()

    def close(self) -> None:
        return None


class _FakePositionPipeline:
    def __init__(self, *reads: PositionReadResult) -> None:
        self._reads = deque(reads)
        self.read_calls = 0
        self.emit_calls = 0

    def read(
        self,
        compass_roi: np.ndarray,
        ts_ms: int,
        *,
        rois: CoordinateRois | None = None,
        emit: bool = True,
    ) -> PositionReadResult:
        self.read_calls += 1
        if not self._reads:
            return PositionReadResult(longitude=None, latitude=None, position=None)
        return self._reads.popleft()

    def emit_read(self, read: PositionReadResult, *, ts_ms: int) -> PositionReadResult:
        self.emit_calls += 1
        return read


def _compass() -> LocatedCompass:
    return LocatedCompass(
        rect=RoiRect(x1=100, x2=360, y1=80, y2=400),
        confidence=0.95,
        scale=1.0,
        center_x=230.0,
        center_y=230.0,
        radius=100.0,
    )


def _digit_rois() -> CoordinateRois:
    return CoordinateRois(
        lon=RoiRect(x1=40, x2=100, y1=250, y2=275),
        lat=RoiRect(x1=40, x2=100, y1=280, y2=305),
        extract_numeric_tokens=False,
    )


def _calibration() -> CoordinateCalibration:
    return CoordinateCalibration(rois=_digit_rois())


def _invalid_read() -> PositionReadResult:
    return PositionReadResult(longitude=None, latitude=None, position=None)


def test_coordinate_ocr_failures_do_not_reacquire_valid_compass() -> None:
    locator = _FakeLocator(_compass())
    calibrator = _FakeCalibrator(_calibration(), None)
    pipeline = _FakePositionPipeline(_invalid_read(), _invalid_read(), _invalid_read())
    runtime = CompassCalibrationRuntime(
        position_pipeline=pipeline,  # type: ignore[arg-type]
        locator=locator,  # type: ignore[arg-type]
        coordinate_calibrator=calibrator,  # type: ignore[arg-type]
        config=CompassCalibrationRuntimeConfig(
            locked_validation_interval_ms=10_000,
            coordinate_recalibration_cooldown_ms=15,
            consecutive_failures_before_recalibrate=2,
        ),
    )
    frame = np.zeros((500, 500, 3), dtype=np.uint8)

    first = runtime.step(frame, ts_ms=100)
    second = runtime.step(frame, ts_ms=110)
    third = runtime.step(frame, ts_ms=120)

    assert not first.reacquire_requested
    assert not second.reacquire_requested
    assert not third.reacquire_requested
    assert locator.locate_calls == 1
    assert calibrator.calls == 2


def test_digit_count_change_is_held_until_text_recalibration() -> None:
    locator = _FakeLocator(_compass())
    calibrator = _FakeCalibrator(_calibration(), _calibration())
    pipeline = _FakePositionPipeline(
        PositionReadResult(longitude=10000, latitude=30125, position=None),
        PositionReadResult(longitude=9999, latitude=30125, position=None),
        PositionReadResult(longitude=9999, latitude=30125, position=None),
    )
    runtime = CompassCalibrationRuntime(
        position_pipeline=pipeline,  # type: ignore[arg-type]
        locator=locator,  # type: ignore[arg-type]
        coordinate_calibrator=calibrator,  # type: ignore[arg-type]
        config=CompassCalibrationRuntimeConfig(
            locked_validation_interval_ms=10_000,
            coordinate_recalibration_cooldown_ms=1,
        ),
    )
    frame = np.zeros((500, 500, 3), dtype=np.uint8)

    first = runtime.step(frame, ts_ms=100)
    second = runtime.step(frame, ts_ms=110)

    assert not first.reacquire_requested
    assert not second.reacquire_requested
    assert calibrator.calls == 2
    assert pipeline.read_calls == 3
    assert pipeline.emit_calls == 2
    assert second.read.longitude == 9999
    assert second.read.latitude == 30125
