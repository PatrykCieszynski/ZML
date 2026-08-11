from __future__ import annotations

from collections import deque

import numpy as np

from zml_ocr_worker.calibration.coordinates import CompassCoordinateLayout
from zml_ocr_worker.calibration.model import LocatedCompass
from zml_ocr_worker.capture.model import RoiRect
from zml_ocr_worker.pipelines.position.pipeline import PositionPipeline


class _FakeDigitsEngine:
    def __init__(self, *responses: str) -> None:
        self._responses = deque(responses)

    def recognize_digits(self, img: np.ndarray) -> str:
        assert img.size > 0
        if not self._responses:
            return ""
        return self._responses.popleft()

    def close(self) -> None:
        return None


def _compass(*, radius: float = 100.0) -> LocatedCompass:
    center_x = 450.0
    center_y = 250.0
    x1 = round(center_x - radius * 1.22)
    y1 = round(center_y - radius * 1.49)
    return LocatedCompass(
        rect=RoiRect(
            x1=x1,
            x2=x1 + round(radius * 2.57),
            y1=y1,
            y2=y1 + round(radius * 2.82),
        ),
        confidence=0.9,
        scale=radius / 142.0,
        center_x=center_x,
        center_y=center_y,
        radius=radius,
    )


def test_coordinate_layout_keeps_fixed_lines_and_progressively_wider_digit_strips() -> None:
    variants = CompassCoordinateLayout().variants(_compass())

    assert [variant.vertical_offset_radius for variant in variants] == [
        0.0,
        -0.03,
        0.03,
        -0.06,
        0.06,
    ]
    nominal = variants[0]
    widths = [candidate.lon.x2 - candidate.lon.x1 for candidate in nominal.roi_candidates]
    assert widths == sorted(widths)
    assert len(set(widths)) == 3

    first = nominal.roi_candidates[0]
    assert first.lon.y1 < first.lon.y2 <= first.lat.y1 < first.lat.y2


def test_coordinate_layout_scales_with_detected_compass_radius() -> None:
    small = CompassCoordinateLayout().variants(_compass(radius=80.0))[0].roi_candidates[-1]
    large = CompassCoordinateLayout().variants(_compass(radius=160.0))[0].roi_candidates[-1]

    small_width = small.lon.x2 - small.lon.x1
    large_width = large.lon.x2 - large.lon.x1
    assert large_width >= small_width * 2 - 2


def test_position_pipeline_reports_success_even_when_position_is_unchanged() -> None:
    rois = CompassCoordinateLayout().variants(_compass())[0].roi_candidates[0]
    engine = _FakeDigitsEngine("61460", "75048", "61460", "75048")
    pipeline = PositionPipeline(rois, engine=engine)  # type: ignore[arg-type]
    compass_roi = np.zeros((282, 257, 3), dtype=np.uint8)
    try:
        first = pipeline.read(compass_roi, ts_ms=1)
        second = pipeline.read(compass_roi, ts_ms=2)
    finally:
        pipeline.close()

    assert first.valid
    assert first.position is not None
    assert second.valid
    assert second.position is None
    assert (second.longitude, second.latitude) == (61460, 75048)


def test_position_pipeline_tries_wider_coordinate_candidates() -> None:
    candidates = CompassCoordinateLayout().variants(_compass())[0].roi_candidates
    engine = _FakeDigitsEngine("", "", "135708", "83952")
    pipeline = PositionPipeline(candidates[0], engine=engine)  # type: ignore[arg-type]
    compass_roi = np.zeros((282, 257, 3), dtype=np.uint8)
    try:
        result = pipeline.read_candidates(compass_roi, ts_ms=1, roi_candidates=candidates)
    finally:
        pipeline.close()

    assert result.valid
    assert (result.longitude, result.latitude) == (135708, 83952)
