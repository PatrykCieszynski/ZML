from __future__ import annotations

from collections import deque

import numpy as np

from zml_ocr_worker.calibration.coordinate_ocr import (
    CoordinateTextCalibrator,
    OcrWord,
    _find_value_word,
    _read_iterator_word,
)
from zml_ocr_worker.capture.model import RoiRect
from zml_ocr_worker.pipelines.position.model import CoordinateRois


class _FakeTextEngine:
    def __init__(self, *responses: tuple[OcrWord, ...]) -> None:
        self._responses = deque(responses)
        self.calls = 0
        self.closed = False

    def recognize_words(self, img: np.ndarray) -> tuple[OcrWord, ...]:
        assert img.size > 0
        self.calls += 1
        if not self._responses:
            return ()
        return self._responses.popleft()

    def close(self) -> None:
        self.closed = True


class _IteratorWithEmptyWord:
    def __init__(self) -> None:
        self.index = 0

    def GetUTF8Text(self, level: object) -> str:
        del level
        if self.index == 0:
            raise RuntimeError("No text returned")
        return "31167"

    def BoundingBox(self, level: object) -> tuple[int, int, int, int]:
        del level
        return (20, 2, 70, 18)

    def Confidence(self, level: object) -> float:
        del level
        return 92.0

    def Next(self, level: object) -> bool:
        del level
        self.index += 1
        return self.index < 2


def _word(text: str, x1: int, x2: int, *, y1: int = 2, y2: int = 16) -> OcrWord:
    return OcrWord(
        text=text,
        rect=RoiRect(x1=x1, x2=x2, y1=y1, y2=y2),
        confidence=0.9,
    )


def test_find_value_word_uses_word_after_label() -> None:
    words = (
        _word("Lon:", 20, 48),
        _word("31167", 60, 102),
        _word("S", 116, 124),
    )

    result = _find_value_word(words, expected_label="lon")

    assert result is not None
    assert result.text == "31167"


def test_find_value_word_tolerates_one_bad_label_character_and_noisy_digits() -> None:
    words = (
        _word("bon:", 20, 48),
        _word("os952", 60, 102),
    )

    result = _find_value_word(words, expected_label="lon")

    assert result is not None
    assert result.text == "os952"


def test_find_value_word_rejects_combined_label_and_value_for_clean_fallback() -> None:
    words = (_word("Lon:31167", 20, 102),)

    assert _find_value_word(words, expected_label="lon") is None


def test_coordinate_text_calibrator_returns_tight_digit_rois_clear_of_labels() -> None:
    engine = _FakeTextEngine(
        (_word("Lon:", 12, 40), _word("31167", 52, 94)),
        (_word("Lat", 18, 44), _word("os952", 60, 94)),
    )
    calibrator = CoordinateTextCalibrator(engine=engine)
    compass_roi = np.zeros((100, 180, 3), dtype=np.uint8)
    search = CoordinateRois(
        lon=RoiRect(x1=20, x2=160, y1=20, y2=40),
        lat=RoiRect(x1=20, x2=160, y1=50, y2=70),
        extract_numeric_tokens=True,
    )

    calibration = calibrator.calibrate(compass_roi, search_rois=search)

    assert calibration is not None
    assert not calibration.rois.extract_numeric_tokens
    assert calibration.rois.lon.x1 == 20 + 52 - 4
    assert calibration.rois.lon.x2 == 20 + 94 + 4
    assert calibration.rois.lat.x1 == 20 + 60 - 4
    assert calibration.rois.lat.x2 == 20 + 94 + 4
    assert calibration.rois.lon.x1 > 20 + 40
    assert calibration.rois.lat.x1 > 20 + 44
    assert engine.calls == 2

    calibrator.close()
    assert engine.closed


def test_iterator_no_text_runtime_error_is_skipped_and_next_word_survives() -> None:
    iterator = _IteratorWithEmptyWord()
    level = object()

    first = _read_iterator_word(iterator, level, upscale=2)
    assert first is None
    assert iterator.Next(level)

    second = _read_iterator_word(iterator, level, upscale=2)
    assert second is not None
    assert second.text == "31167"
    assert second.rect == RoiRect(x1=10, x2=35, y1=1, y2=9)
    assert second.confidence == 0.92
