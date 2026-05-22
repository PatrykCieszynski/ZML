from __future__ import annotations

from typing import Any, Protocol

import numpy as np


class FinderTextEngine(Protocol):
    def recognize_text(self, img: np.ndarray, *, psm: int = 6) -> str: ...

    def close(self) -> None: ...


class PytesseractFinderTextEngine:
    def __init__(self) -> None:
        # TODO: Benchmark a tesserocr-based finder text engine on real finder crops.
        # Position OCR shows tesserocr is much faster, but finder OCR has different text/layout needs.
        try:
            import pytesseract
        except Exception as exc:
            raise RuntimeError(f"pytesseract import failed: {exc}") from exc

        self._pytesseract: Any = pytesseract

    def recognize_text(self, img: np.ndarray, *, psm: int = 6) -> str:
        raw = self._pytesseract.image_to_string(img, config=f"--psm {psm}")
        if isinstance(raw, bytes):
            return raw.decode(errors="replace")
        if isinstance(raw, str):
            return raw
        return ""

    def close(self) -> None:
        pass
