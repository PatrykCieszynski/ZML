from __future__ import annotations

import numpy as np

from zml_ocr_worker.runtime.paths import get_tessdata_dir
from zml_ocr_worker.runtime.tesserocr import preload_tesserocr


class TesserDigitsEngine:
    def __init__(self, *, tessdata_dir: str | None = None) -> None:
        tesserocr = preload_tesserocr()

        resolved_tessdata_dir = get_tessdata_dir(tessdata_dir)

        self._tesserocr = tesserocr
        self._api = tesserocr.PyTessBaseAPI(
            path=str(resolved_tessdata_dir),
            lang="eng",
            psm=tesserocr.PSM.SINGLE_LINE,
            oem=tesserocr.OEM.LSTM_ONLY,
        )
        self._last_confidence: float | None = None

        # Digits-only configuration.
        self._api.SetVariable("tessedit_char_whitelist", "0123456789")
        self._api.SetVariable("classify_bln_numeric_mode", "1")
        self._api.SetVariable("user_defined_dpi", "300")

        # Optional: keep dictionaries off (usually helps for pure digits).
        self._api.SetVariable("load_system_dawg", "0")
        self._api.SetVariable("load_freq_dawg", "0")

        # Optional safety against polarity flips; enable if you see weird inversions in live feed.
        # self._api.SetVariable("tessedit_do_invert", "0")

    @property
    def last_confidence(self) -> float | None:
        return self._last_confidence

    def recognize_digits(self, img_u8: np.ndarray) -> str:
        """
        img_u8: uint8 2D (grayscale/binary). Uses SetImageBytes for speed.
        Returns raw OCR output (may contain whitespace/newlines).
        """
        if img_u8.ndim != 2 or img_u8.dtype != np.uint8:
            raise ValueError(
                f"Expected grayscale/binary uint8 2D image, got {img_u8.dtype} shape={img_u8.shape}"
            )

        img = np.ascontiguousarray(img_u8)
        h, w = img.shape
        self._api.SetImageBytes(img.tobytes(), w, h, 1, w)  # type: ignore[arg-type]
        text = self._api.GetUTF8Text() or ""
        confidence = float(self._api.MeanTextConf()) / 100.0
        self._last_confidence = min(max(confidence, 0.0), 1.0)
        return text

    def close(self) -> None:
        self._api.End()
