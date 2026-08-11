from __future__ import annotations

from collections import deque

import cv2
import numpy as np

from zml_ocr_worker.calibration.coordinates import CompassCoordinateLayout
from zml_ocr_worker.calibration.model import LocatedCompass
from zml_ocr_worker.capture.model import RoiRect
from zml_ocr_worker.pipelines.position.model import CoordinateRois
from zml_ocr_worker.pipelines.position.pipeline import PositionPipeline
from zml_ocr_worker.pipelines.position.token_extractor import NumericTokenExtractor


class _FakeDigitsEngine:
    def __init__(self, *responses: str) -> None:
        self._responses = deque(responses)
        self.calls = 0

    def recognize_digits(self, img: np.ndarray) -> str:
        assert img.size > 0
        self.calls += 1
        if not self._responses:
            return ""
        return self._responses.popleft()

    def close(self) -> None:
        return None


class _FakeConfidenceDigitsEngine:
    def __init__(self, *responses: tuple[str, float]) -> None:
        self._responses = deque(responses)
        self.last_confidence: float | None = None
        self.calls = 0

    def recognize_digits(self, img: np.ndarray) -> str:
        assert img.size > 0
        self.calls += 1
        if not self._responses:
            self.last_confidence = 0.0
            return ""
        text, confidence = self._responses.popleft()
        self.last_confidence = confidence
        return text

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


def _legacy_digit_rois() -> CoordinateRois:
    return CoordinateRois(
        lon=RoiRect(x1=10, x2=70, y1=10, y2=30),
        lat=RoiRect(x1=10, x2=70, y1=35, y2=55),
    )


def _render_right_aligned_line(
    text: str,
    *,
    width: int = 170,
    height: int = 28,
    right_padding: int = 4,
) -> np.ndarray:
    image = np.full((height, width, 3), 32, dtype=np.uint8)
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.55
    thickness = 1
    (text_width, text_height), _ = cv2.getTextSize(text, font, scale, thickness)
    x = width - right_padding - text_width
    y = (height + text_height) // 2 - 2
    cv2.putText(
        image,
        text,
        (x, y),
        font,
        scale,
        (235, 235, 235),
        thickness,
        cv2.LINE_AA,
    )
    return image


def test_coordinate_layout_uses_one_fixed_line_roi_per_vertical_variant() -> None:
    variants = CompassCoordinateLayout().variants(_compass())

    assert [variant.vertical_offset_radius for variant in variants] == [
        0.0,
        -0.03,
        0.03,
        -0.06,
        0.06,
    ]
    nominal = variants[0].rois
    assert nominal.extract_numeric_tokens
    assert nominal.lon.x1 == nominal.lat.x1
    assert nominal.lon.x2 == nominal.lat.x2
    assert nominal.lon.y1 < nominal.lon.y2
    assert nominal.lat.y1 < nominal.lat.y2
    assert nominal.lon.y1 < nominal.lat.y1
    assert nominal.lon.y2 < nominal.lat.y2


def test_coordinate_layout_scales_with_detected_compass_radius() -> None:
    small = CompassCoordinateLayout().variants(_compass(radius=80.0))[0].rois
    large = CompassCoordinateLayout().variants(_compass(radius=160.0))[0].rois

    small_width = small.lon.x2 - small.lon.x1
    large_width = large.lon.x2 - large.lon.x1
    assert large_width >= small_width * 2 - 2


def test_numeric_token_extractor_tracks_five_to_four_digit_transition() -> None:
    extractor = NumericTokenExtractor()

    five_digits = extractor.extract(_render_right_aligned_line("Lon: 10000"))
    four_digits = extractor.extract(_render_right_aligned_line("Lon: 9999"))

    assert five_digits is not None
    assert four_digits is not None
    assert five_digits.shape[1] > four_digits.shape[1]


def test_numeric_token_extractor_ignores_single_trailing_compass_letter() -> None:
    line = np.full((28, 180, 3), 32, dtype=np.uint8)
    coordinate = _render_right_aligned_line("Lon: 10001", width=130, height=28, right_padding=4)
    line[:, :130] = coordinate
    cv2.putText(
        line,
        "S",
        (158, 19),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (235, 235, 235),
        1,
        cv2.LINE_AA,
    )

    token = NumericTokenExtractor().extract(line)

    assert token is not None
    assert token.shape[1] > 25
    assert token.shape[1] < 65


def test_position_pipeline_reports_success_even_when_position_is_unchanged() -> None:
    engine = _FakeDigitsEngine("61460", "75048", "61460", "75048")
    pipeline = PositionPipeline(_legacy_digit_rois(), engine=engine)  # type: ignore[arg-type]
    compass_roi = np.zeros((80, 100, 3), dtype=np.uint8)
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


def test_labeled_coordinate_lines_still_use_only_two_digit_ocr_calls() -> None:
    compass_roi = np.full((70, 180, 3), 32, dtype=np.uint8)
    compass_roi[5:33] = _render_right_aligned_line("Lon: 10000", width=180, height=28)
    compass_roi[37:65] = _render_right_aligned_line("Lat: 30125", width=180, height=28)
    rois = CoordinateRois(
        lon=RoiRect(x1=0, x2=180, y1=5, y2=33),
        lat=RoiRect(x1=0, x2=180, y1=37, y2=65),
        extract_numeric_tokens=True,
    )
    engine = _FakeDigitsEngine("10000", "30125")
    pipeline = PositionPipeline(rois, engine=engine)  # type: ignore[arg-type]
    try:
        result = pipeline.read_candidates(compass_roi, ts_ms=1, roi_candidates=(rois,))
    finally:
        pipeline.close()

    assert result.valid
    assert engine.calls == 2
    assert (result.longitude, result.latitude) == (10000, 30125)


def test_low_confidence_single_layout_is_not_emitted() -> None:
    engine = _FakeConfidenceDigitsEngine(
        ("61460", 0.10),
        ("75048", 0.12),
    )
    rois = _legacy_digit_rois()
    pipeline = PositionPipeline(rois, engine=engine)  # type: ignore[arg-type]
    compass_roi = np.zeros((80, 100, 3), dtype=np.uint8)
    try:
        result = pipeline.read_candidates(compass_roi, ts_ms=1, roi_candidates=(rois,))
    finally:
        pipeline.close()

    assert result.valid
    assert result.confidence == 0.10
    assert not result.is_healthy(min_confidence=0.35)
    assert result.position is None
    assert engine.calls == 2
