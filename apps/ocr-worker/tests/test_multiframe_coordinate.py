from __future__ import annotations

from collections import deque

import numpy as np

from zml_ocr_worker.calibration.coordinate_ocr import CoordinateCalibration
from zml_ocr_worker.calibration.model import LocatedCompass
from zml_ocr_worker.calibration.multiframe_coordinate import (
    MultiFrameCoordinateTextCalibrator,
    MultiFrameCoordinateTextCalibratorConfig,
)
from zml_ocr_worker.calibration.runtime import (
    CompassCalibrationRuntime,
    CompassCalibrationRuntimeConfig,
)
from zml_ocr_worker.capture.model import RoiRect
from zml_ocr_worker.pipelines.position.model import CoordinateRois
from zml_ocr_worker.pipelines.position.pipeline import PositionReadResult


class _StubCoordinateCalibrator:
    def __init__(self, *samples: CoordinateCalibration | None) -> None:
        self._samples = deque(samples)
        self.calls = 0

    def calibrate(
        self,
        compass_roi: np.ndarray,
        *,
        search_rois: CoordinateRois,
    ) -> CoordinateCalibration | None:
        self.calls += 1
        if not self._samples:
            return None
        return self._samples.popleft()

    def close(self) -> None:
        return None


class _SequencedAcquiringCalibrator:
    def __init__(self, calibration: CoordinateCalibration) -> None:
        self._calibration = calibration
        self.calls = 0

    @property
    def acquiring(self) -> bool:
        return 0 < self.calls < 3

    def calibrate(
        self,
        compass_roi: np.ndarray,
        *,
        search_rois: CoordinateRois,
    ) -> CoordinateCalibration | None:
        self.calls += 1
        return self._calibration if self.calls >= 3 else None

    def close(self) -> None:
        return None


class _FakeLocator:
    def __init__(self, compass: LocatedCompass) -> None:
        self._compass = compass

    def locate(self, frame: np.ndarray) -> LocatedCompass | None:
        return self._compass

    def locked_is_valid(self, frame: np.ndarray, compass: LocatedCompass) -> bool:
        return True

    def validate_locked(self, frame: np.ndarray, compass: LocatedCompass) -> float:
        return 1.0


class _FakePositionPipeline:
    def __init__(self) -> None:
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
        return PositionReadResult(longitude=31156, latitude=9515, position=None)

    def emit_read(self, read: PositionReadResult, *, ts_ms: int) -> PositionReadResult:
        self.emit_calls += 1
        return read


def _calibration(*, dx: int = 0, dy: int = 0) -> CoordinateCalibration:
    return CoordinateCalibration(
        rois=CoordinateRois(
            lon=RoiRect(x1=40 + dx, x2=100 + dx, y1=250 + dy, y2=275 + dy),
            lat=RoiRect(x1=42 + dx, x2=102 + dx, y1=280 + dy, y2=305 + dy),
        )
    )


def _search_rois() -> CoordinateRois:
    return CoordinateRois(
        lon=RoiRect(x1=20, x2=140, y1=230, y2=280),
        lat=RoiRect(x1=20, x2=140, y1=270, y2=320),
    )


def _compass() -> LocatedCompass:
    return LocatedCompass(
        rect=RoiRect(x1=100, x2=360, y1=80, y2=400),
        confidence=0.95,
        scale=1.0,
        center_x=230.0,
        center_y=230.0,
        radius=100.0,
    )


def test_multiframe_coordinate_calibrator_uses_median_and_rejects_outlier() -> None:
    base = _StubCoordinateCalibrator(
        _calibration(dx=-1),
        _calibration(dy=1),
        _calibration(dx=1),
        _calibration(),
        _calibration(dx=35, dy=-20),
    )
    calibrator = MultiFrameCoordinateTextCalibrator(
        calibrator=base,  # type: ignore[arg-type]
        config=MultiFrameCoordinateTextCalibratorConfig(sample_count=5, min_inliers=4),
    )
    frame = np.zeros((320, 260, 3), dtype=np.uint8)

    for _ in range(4):
        assert calibrator.calibrate(frame, search_rois=_search_rois()) is None
        assert calibrator.acquiring

    result = calibrator.calibrate(frame, search_rois=_search_rois())

    assert result is not None
    assert not calibrator.acquiring
    assert result.rois.lon == RoiRect(x1=40, x2=100, y1=250, y2=275)
    assert result.rois.lat == RoiRect(x1=42, x2=102, y1=280, y2=305)


def test_multiframe_coordinate_calibrator_requires_consecutive_successes() -> None:
    base = _StubCoordinateCalibrator(
        _calibration(),
        _calibration(),
        None,
        _calibration(),
        _calibration(),
        _calibration(),
        _calibration(),
        _calibration(),
    )
    calibrator = MultiFrameCoordinateTextCalibrator(
        calibrator=base,  # type: ignore[arg-type]
        config=MultiFrameCoordinateTextCalibratorConfig(sample_count=5, min_inliers=4),
    )
    frame = np.zeros((320, 260, 3), dtype=np.uint8)

    assert calibrator.calibrate(frame, search_rois=_search_rois()) is None
    assert calibrator.calibrate(frame, search_rois=_search_rois()) is None
    assert calibrator.acquiring
    assert calibrator.calibrate(frame, search_rois=_search_rois()) is None
    assert not calibrator.acquiring

    result = None
    for _ in range(5):
        result = calibrator.calibrate(frame, search_rois=_search_rois())

    assert result is not None


def test_runtime_samples_coordinate_calibration_at_acquisition_interval() -> None:
    pipeline = _FakePositionPipeline()
    calibrator = _SequencedAcquiringCalibrator(_calibration())
    runtime = CompassCalibrationRuntime(
        position_pipeline=pipeline,  # type: ignore[arg-type]
        locator=_FakeLocator(_compass()),  # type: ignore[arg-type]
        coordinate_calibrator=calibrator,  # type: ignore[arg-type]
        config=CompassCalibrationRuntimeConfig(
            locked_validation_interval_ms=10_000,
            coordinate_acquisition_sample_interval_ms=100,
            coordinate_recalibration_cooldown_ms=2_000,
        ),
    )
    frame = np.zeros((500, 500, 3), dtype=np.uint8)

    first = runtime.step(frame, ts_ms=100)
    assert first.read.position is None
    assert calibrator.calls == 1

    runtime.step(frame, ts_ms=150)
    assert calibrator.calls == 1

    runtime.step(frame, ts_ms=200)
    assert calibrator.calls == 2

    third = runtime.step(frame, ts_ms=300)
    assert calibrator.calls == 3
    assert runtime.active_rois == _calibration().rois
    assert third.read.valid
    assert pipeline.read_calls == 1
    assert pipeline.emit_calls == 1
