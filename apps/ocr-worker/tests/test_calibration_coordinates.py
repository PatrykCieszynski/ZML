from __future__ import annotations

from collections import deque

import numpy as np

from zml_ocr_worker.calibration.coordinates import CompassCoordinateReader
from zml_ocr_worker.calibration.model import LocatedCompass
from zml_ocr_worker.capture.model import RoiRect


class _FakeTextEngine:
    def __init__(self, *responses: str) -> None:
        self._responses = deque(responses)
        self.psm_calls: list[int] = []
        self.image_shapes: list[tuple[int, ...]] = []

    def recognize_text(self, img: np.ndarray, *, psm: int = 6) -> str:
        assert img.size > 0
        self.psm_calls.append(psm)
        self.image_shapes.append(tuple(int(value) for value in img.shape))
        if not self._responses:
            return ""
        return self._responses.popleft()

    def close(self) -> None:
        return None


def _compass() -> LocatedCompass:
    return LocatedCompass(
        rect=RoiRect(x1=300, x2=600, y1=100, y2=430),
        confidence=0.9,
        scale=1.0,
        center_x=450.0,
        center_y=250.0,
        radius=100.0,
    )


def test_coordinate_reader_reads_fixed_lon_and_lat_lines() -> None:
    engine = _FakeTextEngine("Lon: 61460", "Lat: 75048")
    reader = CompassCoordinateReader(text_engine=engine)

    result = reader.read(np.zeros((720, 1280, 3), dtype=np.uint8), _compass())

    assert result.longitude == 61460
    assert result.latitude == 75048
    assert result.has_position
    assert engine.psm_calls == [7, 7]


def test_coordinate_reader_expands_line_width_when_short_crop_is_not_enough() -> None:
    engine = _FakeTextEngine("", "", "", "", "Lon; 135708", "Lat: 83952")
    reader = CompassCoordinateReader(text_engine=engine)

    result = reader.read(np.zeros((720, 1280, 3), dtype=np.uint8), _compass())

    assert result.longitude == 135708
    assert result.latitude == 83952
    assert result.has_position
    first_width = engine.image_shapes[0][1]
    expanded_width = engine.image_shapes[4][1]
    assert expanded_width > first_width


def test_coordinate_reader_preserves_unknown_position_state() -> None:
    engine = _FakeTextEngine("Lon: Unknown N", "Lat: Unknown")
    reader = CompassCoordinateReader(text_engine=engine)

    result = reader.read(np.zeros((720, 1280, 3), dtype=np.uint8), _compass())

    assert result.longitude is None
    assert result.latitude is None
    assert result.longitude_unknown
    assert result.latitude_unknown
    assert not result.has_position
    assert engine.psm_calls == [7, 7]


def test_coordinate_reader_does_not_accept_unlabeled_numbers() -> None:
    engine = _FakeTextEngine("12345", "67890")
    reader = CompassCoordinateReader(text_engine=engine)

    result = reader.read(np.zeros((720, 1280, 3), dtype=np.uint8), _compass())

    assert result.longitude is None
    assert result.latitude is None
    assert not result.longitude_unknown
    assert not result.latitude_unknown
    assert not result.has_position
    assert len(engine.psm_calls) == 32
