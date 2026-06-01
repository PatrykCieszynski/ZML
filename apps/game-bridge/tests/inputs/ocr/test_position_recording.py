from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from zml_game_bridge.inputs.ocr.capture.model import RoiRect
from zml_game_bridge.inputs.ocr.pipelines.position.model import PositionRois
from zml_game_bridge.inputs.ocr.pipelines.position.recording import (
    PositionRoiSnapshotConfig,
    PositionRoiSnapshotRecorder,
    position_roi_snapshot_config_from_env,
)


def test_position_roi_snapshot_recorder_overwrites_fixed_files(tmp_path: Path) -> None:
    recorder = PositionRoiSnapshotRecorder(
        config=PositionRoiSnapshotConfig(enabled=True, root_dir=tmp_path, interval_ms=60_000),
        rois=PositionRois(
            planet=RoiRect(x1=0, x2=1, y1=0, y2=1),
            lon=RoiRect(x1=1, x2=4, y1=1, y2=3),
            lat=RoiRect(x1=4, x2=7, y1=2, y2=5),
        ),
    )

    first = np.full((6, 8, 3), 10, dtype=np.uint8)
    second = np.full((6, 8, 3), 200, dtype=np.uint8)

    recorder.record(first, ts_ms=1_000)
    recorder.record(second, ts_ms=2_000)

    assert sorted(path.name for path in tmp_path.glob("*.png")) == [
        "compass.png",
        "lat.png",
        "lon.png",
    ]
    assert int(cv2.imread(str(tmp_path / "compass.png")).mean()) == 10

    recorder.record(second, ts_ms=61_000)

    assert sorted(path.name for path in tmp_path.glob("*.png")) == [
        "compass.png",
        "lat.png",
        "lon.png",
    ]
    assert int(cv2.imread(str(tmp_path / "compass.png")).mean()) == 200
    assert cv2.imread(str(tmp_path / "lon.png")).shape[:2] == (2, 3)
    assert cv2.imread(str(tmp_path / "lat.png")).shape[:2] == (3, 3)


def test_position_roi_snapshot_recorder_writes_compass_when_child_roi_invalid(
    tmp_path: Path,
) -> None:
    recorder = PositionRoiSnapshotRecorder(
        config=PositionRoiSnapshotConfig(enabled=True, root_dir=tmp_path, interval_ms=60_000),
        rois=PositionRois(
            planet=RoiRect(x1=0, x2=1, y1=0, y2=1),
            lon=RoiRect(x1=20, x2=21, y1=20, y2=21),
            lat=RoiRect(x1=1, x2=3, y1=1, y2=3),
        ),
    )

    recorder.record(np.zeros((6, 8, 3), dtype=np.uint8), ts_ms=1_000)

    assert (tmp_path / "compass.png").exists()
    assert not (tmp_path / "lon.png").exists()
    assert (tmp_path / "lat.png").exists()


def test_position_roi_snapshot_config_from_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ZML_POSITION_ROI_SNAPSHOTS", "0")
    monkeypatch.setenv("ZML_POSITION_ROI_SNAPSHOT_DIR", str(tmp_path))
    monkeypatch.setenv("ZML_POSITION_ROI_SNAPSHOT_INTERVAL_S", "2.5")

    config = position_roi_snapshot_config_from_env()

    assert config.enabled is False
    assert config.root_dir == tmp_path
    assert config.interval_ms == 2_500
