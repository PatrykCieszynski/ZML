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


def test_calibration_snapshot_records_only_suspicious_digit_count_change(tmp_path: Path) -> None:
    compass_roi, compass, rois = _fixture()
    recorder = CalibrationSnapshotRecorder(
        config=CalibrationSnapshotConfig(
            enabled=True,
            root_dir=tmp_path,
            interval_ms=1,
            max_samples=2,
        )
    )

    healthy = recorder.record(
        compass_roi,
        compass=compass,
        rois=rois,
        read=PositionReadResult(
            longitude=10000,
            latitude=30125,
            position=None,
            confidence=0.95,
        ),
        layout_index=0,
        ts_ms=123400,
    )
    sample_dir = recorder.record(
        compass_roi,
        compass=compass,
        rois=rois,
        read=PositionReadResult(
            longitude=9999,
            latitude=30125,
            position=None,
            confidence=0.91,
        ),
        layout_index=0,
        ts_ms=123456,
    )

    assert healthy is None
    assert sample_dir is not None
    assert sample_dir == tmp_path / "sample-123456-digit-count-changed"
    assert (sample_dir / "overview.png").exists()
    assert (sample_dir / "lon-line.png").exists()
    assert (sample_dir / "lat-line.png").exists()
    assert (sample_dir / "meta.txt").exists()
    assert not (sample_dir / "lon-mask.png").exists()
    assert not (sample_dir / "lat-mask.png").exists()

    metadata = (sample_dir / "meta.txt").read_text(encoding="utf-8")
    assert "reason=digit-count-changed" in metadata
    assert "ocr_lon=9999" in metadata
    assert "ocr_lat=30125" in metadata
    assert "ocr_confidence=0.910" in metadata


def test_calibration_snapshot_records_repeated_invalid_read_at_threshold(tmp_path: Path) -> None:
    compass_roi, compass, rois = _fixture()
    recorder = CalibrationSnapshotRecorder(
        config=CalibrationSnapshotConfig(
            enabled=True,
            root_dir=tmp_path,
            interval_ms=1,
            max_samples=3,
            invalid_streak_threshold=3,
        )
    )

    results = [
        recorder.record(
            compass_roi,
            compass=compass,
            rois=rois,
            read=PositionReadResult(longitude=None, latitude=None, position=None),
            layout_index=0,
            ts_ms=ts_ms,
        )
        for ts_ms in (1000, 1100, 1200, 1300)
    ]

    assert results[:2] == [None, None]
    assert results[2] == tmp_path / "sample-1200-repeated-invalid-read"
    assert results[3] is None


def test_calibration_snapshot_records_low_confidence_only_on_state_entry(tmp_path: Path) -> None:
    compass_roi, compass, rois = _fixture()
    recorder = CalibrationSnapshotRecorder(
        config=CalibrationSnapshotConfig(
            enabled=True,
            root_dir=tmp_path,
            interval_ms=1,
            max_samples=3,
            low_confidence_threshold=0.15,
        )
    )

    first = recorder.record(
        compass_roi,
        compass=compass,
        rois=rois,
        read=PositionReadResult(
            longitude=31156,
            latitude=9515,
            position=None,
            confidence=0.10,
        ),
        layout_index=0,
        ts_ms=1000,
    )
    second = recorder.record(
        compass_roi,
        compass=compass,
        rois=rois,
        read=PositionReadResult(
            longitude=31155,
            latitude=9515,
            position=None,
            confidence=0.08,
        ),
        layout_index=0,
        ts_ms=1100,
    )
    recorder.record(
        compass_roi,
        compass=compass,
        rois=rois,
        read=PositionReadResult(
            longitude=31154,
            latitude=9515,
            position=None,
            confidence=0.90,
        ),
        layout_index=0,
        ts_ms=1200,
    )
    third = recorder.record(
        compass_roi,
        compass=compass,
        rois=rois,
        read=PositionReadResult(
            longitude=31153,
            latitude=9515,
            position=None,
            confidence=0.09,
        ),
        layout_index=0,
        ts_ms=1300,
    )

    assert first is not None
    assert second is None
    assert third is not None


def _fixture() -> tuple[np.ndarray, LocatedCompass, CoordinateRois]:
    compass_roi = np.full((180, 260, 3), 25, dtype=np.uint8)
    lon_roi = RoiRect(x1=70, x2=230, y1=105, y2=130)
    lat_roi = RoiRect(x1=70, x2=230, y1=135, y2=160)
    _draw_right_aligned_line(compass_roi, lon_roi, "Lon: 10000")
    _draw_right_aligned_line(compass_roi, lat_roi, "Lat: 30125")
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
        extract_numeric_tokens=False,
    )
    return compass_roi, compass, rois


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
