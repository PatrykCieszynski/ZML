from __future__ import annotations

from collections import deque

import numpy as np

from zml_ocr_worker.calibration.coordinate_ocr import CoordinateCalibration
from zml_ocr_worker.calibration.model import LocatedCompass
from zml_ocr_worker.calibration.persistence import PersistedCompassCalibration
from zml_ocr_worker.calibration.runtime import (
    CompassCalibrationRuntime,
    CompassCalibrationRuntimeConfig,
)
from zml_ocr_worker.capture.model import RoiRect
from zml_ocr_worker.pipelines.position.model import CoordinateRois
from zml_ocr_worker.pipelines.position.pipeline import PositionReadResult


class _FakeStore:
    def __init__(self, loaded: PersistedCompassCalibration | None = None) -> None:
        self.loaded = loaded
        self.load_calls = 0
        self.saved: list[PersistedCompassCalibration] = []

    def load(self) -> PersistedCompassCalibration | None:
        self.load_calls += 1
        return self.loaded

    def save(self, state: PersistedCompassCalibration) -> bool:
        self.saved.append(state)
        return True


class _FakeLocator:
    def __init__(self, compass: LocatedCompass, *, locked_valid: bool = True) -> None:
        self._compass = compass
        self._locked_valid = locked_valid
        self.locate_calls = 0
        self.locked_calls = 0

    def locate(self, frame: np.ndarray) -> LocatedCompass | None:
        self.locate_calls += 1
        return self._compass

    def locked_is_valid(self, frame: np.ndarray, compass: LocatedCompass) -> bool:
        self.locked_calls += 1
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
    )


def _calibration() -> CoordinateCalibration:
    return CoordinateCalibration(rois=_digit_rois())


def _read() -> PositionReadResult:
    return PositionReadResult(longitude=31156, latitude=9515, position=None)


def test_runtime_restores_persisted_compass_without_full_reacquire() -> None:
    persisted = PersistedCompassCalibration(
        frame_width=500,
        frame_height=500,
        compass=_compass(),
        rois=_digit_rois(),
    )
    store = _FakeStore(persisted)
    locator = _FakeLocator(_compass())
    calibrator = _FakeCalibrator()
    pipeline = _FakePositionPipeline(_read())
    runtime = CompassCalibrationRuntime(
        position_pipeline=pipeline,  # type: ignore[arg-type]
        locator=locator,  # type: ignore[arg-type]
        coordinate_calibrator=calibrator,  # type: ignore[arg-type]
        state_store=store,  # type: ignore[arg-type]
        config=CompassCalibrationRuntimeConfig(locked_validation_interval_ms=10_000),
    )
    frame = np.zeros((500, 500, 3), dtype=np.uint8)

    step = runtime.step(frame, ts_ms=100)

    assert step.compass == persisted.compass
    assert runtime.active_rois == persisted.rois
    assert locator.locate_calls == 0
    assert locator.locked_calls >= 2
    assert calibrator.calls == 0
    assert pipeline.emit_calls == 1
    assert not store.saved


def test_runtime_persists_new_calibration_after_ten_consecutive_valid_reads() -> None:
    store = _FakeStore()
    locator = _FakeLocator(_compass())
    calibrator = _FakeCalibrator(_calibration())
    pipeline = _FakePositionPipeline(*[_read() for _ in range(10)])
    runtime = CompassCalibrationRuntime(
        position_pipeline=pipeline,  # type: ignore[arg-type]
        locator=locator,  # type: ignore[arg-type]
        coordinate_calibrator=calibrator,  # type: ignore[arg-type]
        state_store=store,  # type: ignore[arg-type]
        config=CompassCalibrationRuntimeConfig(
            locked_validation_interval_ms=10_000,
            verified_reads_before_persist=10,
        ),
    )
    frame = np.zeros((500, 500, 3), dtype=np.uint8)

    for index in range(9):
        runtime.step(frame, ts_ms=100 + index * 10)
        assert not store.saved

    runtime.step(frame, ts_ms=190)

    assert len(store.saved) == 1
    saved = store.saved[0]
    assert saved.frame_width == 500
    assert saved.frame_height == 500
    assert saved.compass == _compass()
    assert saved.rois == _digit_rois()
