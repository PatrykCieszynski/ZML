from __future__ import annotations

from typing import Any, Protocol

import numpy as np

from zml_ocr_agent.paths import get_tessdata_dir
from zml_ocr_agent.pipelines.image import to_gray_u8
from zml_ocr_agent.tesserocr_runtime import preload_tesserocr


class FinderTextEngine(Protocol):
    def recognize_text(self, img: np.ndarray, *, psm: int = 6) -> str: ...

    def close(self) -> None: ...


class TesserocrFinderTextEngine:
    def __init__(
        self,
        *,
        tessdata_dir: str | None = None,
        tesserocr_module: Any | None = None,
    ) -> None:
        tesserocr = tesserocr_module or preload_tesserocr()
        resolved_tessdata_dir = get_tessdata_dir(tessdata_dir)

        self._api = tesserocr.PyTessBaseAPI(
            path=str(resolved_tessdata_dir),
            lang="eng",
            psm=tesserocr.PSM.SINGLE_BLOCK,
            oem=tesserocr.OEM.LSTM_ONLY,
        )
        self._api.SetVariable("user_defined_dpi", "300")
        self._api.SetVariable("load_system_dawg", "0")
        self._api.SetVariable("load_freq_dawg", "0")

    def recognize_text(self, img: np.ndarray, *, psm: int = 6) -> str:
        gray = np.ascontiguousarray(to_gray_u8(img))
        height, width = gray.shape
        self._api.SetPageSegMode(psm)
        self._api.SetImageBytes(gray.tobytes(), width, height, 1, width)
        return self._api.GetUTF8Text() or ""

    def close(self) -> None:
        self._api.End()
