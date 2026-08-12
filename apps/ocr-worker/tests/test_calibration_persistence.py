from __future__ import annotations

import json
from pathlib import Path

from zml_ocr_worker.calibration.model import LocatedCompass
from zml_ocr_worker.calibration.persistence import (
    CompassCalibrationStore,
    PersistedCompassCalibration,
    default_compass_calibration_path,
)
from zml_ocr_worker.capture.model import RoiRect
from zml_ocr_worker.pipelines.position.model import CoordinateRois


def _state() -> PersistedCompassCalibration:
    return PersistedCompassCalibration(
        frame_width=2560,
        frame_height=1440,
        compass=LocatedCompass(
            rect=RoiRect(x1=2190, x2=2551, y1=965, y2=1411),
            confidence=0.94,
            scale=1.0,
            center_x=2363.0,
            center_y=1177.0,
            radius=142.0,
        ),
        rois=CoordinateRois(
            lon=RoiRect(x1=85, x2=145, y1=350, y2=370),
            lat=RoiRect(x1=90, x2=145, y1=375, y2=395),
        ),
    )


def test_compass_calibration_store_round_trips_state(tmp_path: Path) -> None:
    path = tmp_path / "config" / "compass_calibration.json"
    store = CompassCalibrationStore(path)
    state = _state()

    assert store.save(state)
    assert store.load() == state
    assert not path.with_name("compass_calibration.json.tmp").exists()


def test_compass_calibration_store_rejects_corrupt_state(tmp_path: Path) -> None:
    path = tmp_path / "compass_calibration.json"
    path.write_text(json.dumps({"version": 1, "frame": {}}), encoding="utf-8")

    assert CompassCalibrationStore(path).load() is None


def test_default_compass_calibration_path_honors_env(
    tmp_path: Path,
    monkeypatch,
) -> None:
    expected = tmp_path / "saved.json"
    monkeypatch.setenv("ZML_COMPASS_CALIBRATION_PATH", str(expected))

    assert default_compass_calibration_path() == expected
