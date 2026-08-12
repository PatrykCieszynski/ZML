from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

import cv2
import numpy as np

from zml_ocr_worker.capture.model import RoiRect
from zml_ocr_worker.pipelines.image import to_gray_u8
from zml_ocr_worker.pipelines.position.model import CoordinateRois
from zml_ocr_worker.runtime.paths import get_tessdata_dir
from zml_ocr_worker.runtime.tesserocr import preload_tesserocr


@dataclass(frozen=True, slots=True)
class OcrWord:
    text: str
    rect: RoiRect
    confidence: float | None = None


class CoordinateTextEngine(Protocol):
    def recognize_words(self, img: np.ndarray) -> tuple[OcrWord, ...]: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class CoordinateCalibration:
    rois: CoordinateRois
    longitude_digits: int
    latitude_digits: int


class TesserocrCoordinateTextEngine:
    """Occasional full-text OCR used only to anchor Lon/Lat numeric ROIs."""

    def __init__(
        self,
        *,
        tessdata_dir: str | None = None,
        tesserocr_module: Any | None = None,
        upscale: int = 2,
    ) -> None:
        tesserocr = tesserocr_module or preload_tesserocr()
        resolved_tessdata_dir = get_tessdata_dir(tessdata_dir)
        self._tesserocr = tesserocr
        self._upscale = max(1, int(upscale))
        self._api = tesserocr.PyTessBaseAPI(
            path=str(resolved_tessdata_dir),
            lang="eng",
            psm=tesserocr.PSM.SINGLE_LINE,
            oem=tesserocr.OEM.LSTM_ONLY,
        )
        self._api.SetVariable("user_defined_dpi", "300")
        self._api.SetVariable("load_system_dawg", "0")
        self._api.SetVariable("load_freq_dawg", "0")

    def recognize_words(self, img: np.ndarray) -> tuple[OcrWord, ...]:
        prepared = _prepare_text_line(img, upscale=self._upscale)
        height, width = prepared.shape
        self._api.SetPageSegMode(self._tesserocr.PSM.SINGLE_LINE)
        self._api.SetImageBytes(prepared.tobytes(), width, height, 1, width)
        self._api.Recognize()
        iterator = self._api.GetIterator()
        if iterator is None:
            return ()

        level = self._tesserocr.RIL.WORD
        words: list[OcrWord] = []
        while True:
            text = (iterator.GetUTF8Text(level) or "").strip()
            bbox = iterator.BoundingBox(level)
            if text and bbox is not None:
                x1, y1, x2, y2 = (int(value) for value in bbox)
                scale = self._upscale
                rect = RoiRect(
                    x1=max(0, round(x1 / scale)),
                    x2=max(1, round(x2 / scale)),
                    y1=max(0, round(y1 / scale)),
                    y2=max(1, round(y2 / scale)),
                )
                confidence_raw = iterator.Confidence(level)
                confidence = (
                    min(max(float(confidence_raw) / 100.0, 0.0), 1.0)
                    if confidence_raw is not None
                    else None
                )
                words.append(OcrWord(text=text, rect=rect, confidence=confidence))
            if not iterator.Next(level):
                break
        return tuple(words)

    def close(self) -> None:
        self._api.End()


class CoordinateTextCalibrator:
    """Find numeric value boxes after Lon:/Lat: using occasional text OCR."""

    def __init__(self, *, engine: CoordinateTextEngine | None = None) -> None:
        self._engine = engine or TesserocrCoordinateTextEngine()

    def calibrate(
        self,
        compass_roi: np.ndarray,
        *,
        search_rois: CoordinateRois,
    ) -> CoordinateCalibration | None:
        lon = self._calibrate_line(
            compass_roi,
            line_roi=search_rois.lon,
            expected_label="lon",
        )
        lat = self._calibrate_line(
            compass_roi,
            line_roi=search_rois.lat,
            expected_label="lat",
        )
        if lon is None or lat is None:
            return None

        lon_roi, lon_digits = lon
        lat_roi, lat_digits = lat
        return CoordinateCalibration(
            rois=CoordinateRois(
                lon=lon_roi,
                lat=lat_roi,
                extract_numeric_tokens=False,
            ),
            longitude_digits=lon_digits,
            latitude_digits=lat_digits,
        )

    def close(self) -> None:
        self._engine.close()

    def _calibrate_line(
        self,
        compass_roi: np.ndarray,
        *,
        line_roi: RoiRect,
        expected_label: str,
    ) -> tuple[RoiRect, int] | None:
        line = line_roi.crop(compass_roi)
        if line is None:
            return None
        words = self._engine.recognize_words(line)
        value = _find_value_word(words, expected_label=expected_label)
        if value is None:
            return None
        value_word, digits = value

        line_height = max(1, line_roi.y2 - line_roi.y1)
        horizontal_pad = max(2, round(line_height * 0.18))
        vertical_pad = max(1, round(line_height * 0.08))
        rect = RoiRect(
            x1=max(line_roi.x1, line_roi.x1 + value_word.rect.x1 - horizontal_pad),
            x2=min(line_roi.x2, line_roi.x1 + value_word.rect.x2 + horizontal_pad),
            y1=max(line_roi.y1, line_roi.y1 + value_word.rect.y1 - vertical_pad),
            y2=min(line_roi.y2, line_roi.y1 + value_word.rect.y2 + vertical_pad),
        )
        if rect.x2 <= rect.x1 or rect.y2 <= rect.y1:
            return None
        return rect, len(digits)


def _find_value_word(
    words: tuple[OcrWord, ...],
    *,
    expected_label: str,
) -> tuple[OcrWord, str] | None:
    label_index: int | None = None
    for index, word in enumerate(words):
        normalized = re.sub(r"[^a-z:]", "", word.text.lower())
        if expected_label in normalized:
            label_index = index
            combined_digits = "".join(char for char in word.text if char.isdigit())
            if combined_digits:
                # A combined "Lon:12345" word has no reliable per-token bbox. Let
                # calibration fail cleanly; template matching is the planned fallback.
                return None
            break
    if label_index is None:
        return None

    for word in words[label_index + 1 :]:
        digits = "".join(char for char in word.text if char.isdigit())
        if 3 <= len(digits) <= 7:
            return word, digits
    return None


def _prepare_text_line(img: np.ndarray, *, upscale: int) -> np.ndarray:
    gray = to_gray_u8(img)
    if upscale > 1:
        gray = cv2.resize(
            gray,
            None,
            fx=upscale,
            fy=upscale,
            interpolation=cv2.INTER_CUBIC,
        )
    kernel_size = max(3, round(gray.shape[0] * 0.45))
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
    top = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, kernel)
    _, binary = cv2.threshold(top, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if float(np.count_nonzero(binary)) / float(binary.size) < 0.5:
        binary = cv2.bitwise_not(binary)
    return np.ascontiguousarray(binary)
