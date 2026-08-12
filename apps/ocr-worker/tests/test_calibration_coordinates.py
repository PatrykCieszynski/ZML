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


class _MaskBackedTokenExtractor(NumericTokenExtractor):
    def __init__(self, mask: np.ndarray) -> None:
        super().__init__()
        self._mask = mask

    def _text_mask(self, gray: np.ndarray) -> np.ndarray:
        assert gray.shape == self._mask.shape
        return self._mask


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
            y2=y1 + round(radius * 3.14),
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


def test_coordinate_layout_uses_one_wide_deterministic_strip_pair() -> None:
    variants = CompassCoordinateLayout().variants(_compass())

    assert len(variants) == 1
    assert variants[0].vertical_offset_radius == 0.0
    rois = variants[0].rois
    assert not rois.extract_numeric_tokens
    assert rois.lon.x1 == rois.lat.x1
    assert rois.lon.x2 == rois.lat.x2
    assert rois.lon.x1 <= 1
    assert rois.lon.x2 - rois.lon.x1 >= 135
    assert rois.lon.y1 < rois.lon.y2 < rois.lat.y1 < rois.lat.y2


def test_coordinate_layout_scales_with_detected_compass_radius() -> None:
    small = CompassCoordinateLayout().variants(_compass(radius=80.0))[0].rois
    large = CompassCoordinateLayout().variants(_compass(radius=160.0))[0].rois

    small_width = small.lon.x2 - small.lon.x1
    large_width = large.lon.x2 - large.lon.x1
    assert large_width >= small_width * 2 - 2

    small_lon_height = small.lon.y2 - small.lon.y1
    large_lon_height = large.lon.y2 - large.lon.y1
    assert large_lon_height >= small_lon_height * 2 - 2


def test_numeric_token_extractor_tracks_five_to_four_digit_transition() -> None:
    extractor = NumericTokenExtractor()

    five_digits = extractor.extract(_render_right_aligned_line("Lon: 10000"))
    four_digits = extractor.extract(_render_right_aligned_line("Lon: 9999"))

    assert five_digits is not None
    assert four_digits is not None
    assert five_digits.shape[1] > four_digits.shape[1]


def test_numeric_token_extractor_keeps_narrow_digit_spacing_in_one_token() -> None:
    # Regression for a real 21 px Entropia Lon line. Its foreground projection
    # contained a 5 px gap between narrow numeric glyphs, while the actual
    # label/value separator was 12 px. The old 0.18h threshold split 31167 into
    # 31 + 167 and sent only 167 to digit OCR.
    mask = np.zeros((21, 123), dtype=np.uint8)
    runs = (
        (36, 44),
        (45, 54),
        (56, 64),
        (76, 84),
        (86, 91),
        (96, 101),
        (105, 114),
        (115, 123),
    )
    for x1, x2 in runs:
        mask[4:18, x1:x2] = 255

    line = np.zeros((21, 123, 3), dtype=np.uint8)
    analysis = _MaskBackedTokenExtractor(mask).analyze(line)

    assert analysis.token is not None
    assert analysis.x1 == 75
    assert analysis.x2 == 123
    assert analysis.token.shape[1] == 48


def test_numeric_token_extractor_falls_back_to_bounded_right_suffix() -> None:
    # Community screenshots can render Lat and its value so tightly that the
    # morphology sees one merged cluster instead of a separate label/value pair.
    mask = np.zeros((17, 130), dtype=np.uint8)
    runs = (
        (40, 47),
        (49, 55),
        (57, 64),
        (66, 69),
        (71, 78),
        (80, 87),
        (89, 96),
        (98, 105),
        (107, 114),
    )
    for x1, x2 in runs:
        mask[3:14, x1:x2] = 255

    line = np.zeros((17, 130, 3), dtype=np.uint8)
    analysis = _MaskBackedTokenExtractor(mask).analyze(line)

    assert analysis.token is not None
    assert analysis.x2 == 115
    assert analysis.token.shape[1] <= round(17 * 3.2)
    assert analysis.token.shape[1] >= 40


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
