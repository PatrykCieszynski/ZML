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

    def recognize_text(self, img: np.ndarray, *, psm: int = 6) -> str:
        assert img.size > 0
        self.psm_calls.append(psm)
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


def test_coordinate_reader_reads_both_values_from_broad_region() -> None:
    engine = _FakeTextEngine("Lon: 61460\nLat: 75048")
    reader = CompassCoordinateReader(text_engine=engine)

    result = reader.read(np.zeros((720, 1280, 3), dtype=np.uint8), _compass())

    assert result.longitude == 61460
    assert result.latitude == 75048
    assert result.has_position
    assert engine.psm_calls == [6]


def test_coordinate_reader_falls_back_only_for_missing_line() -> None:
    engine = _FakeTextEngine("Lon; 135708", "Lat: 83952")
    reader = CompassCoordinateReader(text_engine=engine)

    result = reader.read(np.zeros((720, 1280, 3), dtype=np.uint8), _compass())

    assert result.longitude == 135708
    assert result.latitude == 83952
    assert result.has_position
    assert engine.psm_calls == [6, 11]


def test_coordinate_reader_preserves_unknown_position_state() -> None:
    engine = _FakeTextEngine("Lon: Unknown N\nLat: Unknown")
    reader = CompassCoordinateReader(text_engine=engine)

    result = reader.read(np.zeros((720, 1280, 3), dtype=np.uint8), _compass())

    assert result.longitude is None
    assert result.latitude is None
    assert result.longitude_unknown
    assert result.latitude_unknown
    assert not result.has_position
    assert engine.psm_calls == [6]


def test_coordinate_reader_does_not_accept_unlabeled_numbers() -> None:
    engine = _FakeTextEngine("12345 67890", "99999", "88888")
    reader = CompassCoordinateReader(text_engine=engine)

    result = reader.read(np.zeros((720, 1280, 3), dtype=np.uint8), _compass())

    assert result.longitude is None
    assert result.latitude is None
    assert not result.longitude_unknown
    assert not result.latitude_unknown
    assert not result.has_position
    assert engine.psm_calls == [6, 11, 11]
