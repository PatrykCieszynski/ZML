from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from zml_ocr_worker.calibration.model import LocatedCompass
from zml_ocr_worker.calibration.recording import (
    CalibrationSnapshotConfig,
    CalibrationSnapshotRecorder,
)
from zml_ocr_worker.capture.model import RoiRect
from zml_ocr_worker.pipelines.position.model import CoordinateRois
from zml_ocr_worker.pipelines.position.pipeline import PositionReadResult


def test_calibration_snapshot_records_visual_pipeline_crops(tmp_path: Path) -> None:
    compass_roi = np.full((180, 260, 3), 25, dtype=np.uint8)
    lon_roi = RoiRect(x1=70, x2=230, y1=105, y2=130)
    lat_roi = RoiRect(x1=70, x2=230, y1=135, y2=160)
    _draw_right_aligned_line(compass_roi, lon_roi, "Lon: 10000")
    _draw_right_aligned_line(compass_roi, lat_roi, "Lat: 30125")

    recorder = CalibrationSnapshotRecorder(
        config=CalibrationSnapshotConfig(
            enabled=True,
            root_dir=tmp_path,
            interval_ms=1,
            max_samples=2,
        )
    )
    compass = LocatedCompass(
        rect=RoiRect(x1=1000, x2=1260, y1=700, y2=880),
        confidence=0.94,
        scale=1.0,
        center_x=1130.0,
        center_y=790.0,
        radius=100.0,
    )
    rois = CoordinateRois(
        lon=lon_roi,
        lat=lat_roi,
        extract_numeric_tokens=True,
    )
    read = PositionReadResult(
        longitude=10000,
        latitude=30125,
        position=None,
        confidence=0.0,
    )

    sample_dir = recorder.record(
        compass_roi,
        compass=compass,
        rois=rois,
        read=read,
        layout_index=0,
        ts_ms=123456,
    )

    assert sample_dir is not None
    assert sample_dir == tmp_path / "sample-123456"
    assert (sample_dir / "overview.png").exists()
    assert (sample_dir / "lon-line.png").exists()
    assert (sample_dir / "lat-line.png").exists()
    assert (sample_dir / "lon-mask.png").exists()
    assert (sample_dir / "lat-mask.png").exists()
    assert (sample_dir / "lon-token.png").exists()
    assert (sample_dir / "lat-token.png").exists()
    assert (tmp_path / "latest-overview.png").exists()
    assert (tmp_path / "latest-lon-token.png").exists()
    assert (tmp_path / "latest-lat-token.png").exists()

    metadata = (tmp_path / "latest-meta.txt").read_text(encoding="utf-8")
    assert "layout_index=0" in metadata
    assert "ocr_lon=10000" in metadata
    assert "ocr_lat=30125" in metadata
    assert "ocr_confidence=0.000" in metadata


def test_position_text_log_records_every_read_without_visual_snapshots(tmp_path: Path) -> None:
    log_path = tmp_path / "position.tsv"
    recorder = CalibrationSnapshotRecorder(
        config=CalibrationSnapshotConfig(
            enabled=False,
            root_dir=tmp_path / "unused-visuals",
            text_log_enabled=True,
            text_log_path=log_path,
        )
    )
    compass = LocatedCompass(
        rect=RoiRect(x1=100, x2=360, y1=80, y2=400),
        confidence=0.95,
        scale=1.0,
        center_x=230.0,
        center_y=230.0,
        radius=100.0,
    )
    rois = CoordinateRois(
        lon=RoiRect(x1=40, x2=100, y1=250, y2=275),
        lat=RoiRect(x1=40, x2=100, y1=280, y2=305),
        extract_numeric_tokens=False,
    )
    frame = np.zeros((320, 260, 3), dtype=np.uint8)

    recorder.record(
        frame,
        compass=compass,
        rois=rois,
        read=PositionReadResult(
            longitude=31156,
            latitude=9515,
            position=None,
            confidence=0.24,
        ),
        layout_index=0,
        ts_ms=1000,
    )
    recorder.record(
        frame,
        compass=compass,
        rois=rois,
        read=PositionReadResult(longitude=None, latitude=None, position=None),
        layout_index=0,
        ts_ms=1100,
    )

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert lines[0].startswith("ts_ms\tlon\tlat\tconfidence\tvalid\temitted")
    assert "1000\t31156\t9515\t0.240\t1\t0" in lines[1]
    assert "1100\t\t\t\t0\t0" in lines[2]
    assert not (tmp_path / "unused-visuals").exists()


def _draw_right_aligned_line(image: np.ndarray, roi: RoiRect, text: str) -> None:
    crop = np.ascontiguousarray(image[roi.y1 : roi.y2, roi.x1 : roi.x2].copy())
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.55
    thickness = 1
    (text_width, text_height), _ = cv2.getTextSize(text, font, scale, thickness)
    x = max(0, crop.shape[1] - text_width - 4)
    y = min(crop.shape[0] - 2, (crop.shape[0] + text_height) // 2 - 1)
    cv2.putText(
        crop,
        text,
        (x, y),
        font,
        scale,
        (235, 235, 235),
        thickness,
        cv2.LINE_AA,
    )
    image[roi.y1 : roi.y2, roi.x1 : roi.x2] = crop
