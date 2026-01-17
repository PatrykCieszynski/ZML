from __future__ import annotations

from pathlib import Path

import numpy as np

import zml_game_bridge


class TesserDigitsEngine:
    def __init__(self, *, tessdata_dir: str | None = None) -> None:
        try:
            import tesserocr  # type: ignore
        except Exception as e:
            raise RuntimeError(f"tesserocr import failed: {e}") from e

        self._tesserocr = tesserocr

        if tessdata_dir is None:
            tessdata_dir = str(Path(zml_game_bridge.__file__).resolve().parent.parent.parent / "resources" / "tessdata/")
        if not tessdata_dir:
            raise RuntimeError("Missing tessdata path. Set TESSDATA_PREFIX or pass tessdata_dir explicitly.")

        self._api = tesserocr.PyTessBaseAPI(
            path=tessdata_dir,
            lang="eng",
            psm=tesserocr.PSM.SINGLE_LINE,
            oem=tesserocr.OEM.LSTM_ONLY,
        )

        # Digits-only configuration.
        self._api.SetVariable("tessedit_char_whitelist", "0123456789")
        self._api.SetVariable("classify_bln_numeric_mode", "1")
        self._api.SetVariable("user_defined_dpi", "300")

        # Optional: keep dictionaries off (usually helps for pure digits).
        self._api.SetVariable("load_system_dawg", "0")
        self._api.SetVariable("load_freq_dawg", "0")

        # Optional safety against polarity flips; enable if you see weird inversions in live feed.
        # self._api.SetVariable("tessedit_do_invert", "0")

    def recognize_digits(self, img_u8: np.ndarray) -> str:
        """
        img_u8: uint8 2D (grayscale/binary). Uses SetImageBytes for speed.
        Returns raw OCR output (may contain whitespace/newlines).
        """
        if img_u8.ndim != 2 or img_u8.dtype != np.uint8:
            raise ValueError(f"Expected grayscale/binary uint8 2D image, got {img_u8.dtype} shape={img_u8.shape}")

        img = np.ascontiguousarray(img_u8)
        h, w = img.shape
        self._api.SetImageBytes(img.tobytes(), w, h, 1, w)
        return self._api.GetUTF8Text() or ""

    def close(self) -> None:
        self._api.End()
