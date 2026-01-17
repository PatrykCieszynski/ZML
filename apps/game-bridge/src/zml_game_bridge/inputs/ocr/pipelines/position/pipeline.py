from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from zml_game_bridge.common.models import WorldPos
from zml_game_bridge.inputs.ocr.pipelines.position.engine import TesserDigitsEngine
from zml_game_bridge.inputs.ocr.pipelines.position.model import PositionRois, OcrPosition
from zml_game_bridge.inputs.ocr.pipelines.position.preprocess import (
    DigitsPreprocessConfig,
    DigitsPreprocessor
)


@dataclass(frozen=True, slots=True)
class PositionPipelineConfig:
    sanity_min: int = 1000
    sanity_max: int = 10_000_000


class PositionPipeline:
    def __init__(
        self,
        rois: PositionRois,
        *,
        engine: TesserDigitsEngine | None = None,
        pre_cfg: DigitsPreprocessConfig | None = None,
        cfg: PositionPipelineConfig | None = None,
    ) -> None:
        self._rois = rois
        self._engine = engine or TesserDigitsEngine()
        self._pre_cfg = pre_cfg or DigitsPreprocessConfig()
        self._pre = DigitsPreprocessor(pre_cfg)
        self._cfg = cfg or PositionPipelineConfig()

        self._last_emitted: tuple[int, int] | None = None

    def close(self) -> None:
        self._engine.close()

    def step(self, compass_roi: np.ndarray, ts_ms: int) -> OcrPosition | None:
        lon_img = self._rois.lon.crop(compass_roi)
        lat_img = self._rois.lat.crop(compass_roi)

        if lon_img is None or lat_img is None:
            return None
        lon = self._read_int(lon_img)
        lat = self._read_int(lat_img)
        # TODO range check lat/lon?

        if lon is None or lat is None:
            return None
        if (lon, lat) == self._last_emitted:
            return None

        self._last_emitted = (lon, lat)

        return OcrPosition(
            ts_ms=ts_ms,
            position=WorldPos(
                planet_name="",  # fill later when planet OCR returns
                x=lon,
                y=lat,
                z=None,
            ),
        )

    def _read_int(self, img: np.ndarray) -> int | None:
        pre = self._pre.process(img)
        raw = self._engine.recognize_digits(pre)

        digits = self._digits_only(raw)
        if not digits:
            return None

        try:
            val = int(digits)
        except ValueError:
            return None

        if not (self._cfg.sanity_min <= val <= self._cfg.sanity_max):
            return None

        return val

    @staticmethod
    def _digits_only(text: str) -> str:
        # Keep only [0-9] to avoid false positives from OCR artifacts.
        return "".join(ch for ch in text if "0" <= ch <= "9")
