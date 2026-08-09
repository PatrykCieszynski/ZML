from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from zml_ocr_agent.models import WorldPosition
from zml_ocr_agent.pipelines.position.engine import TesserDigitsEngine
from zml_ocr_agent.pipelines.position.model import OcrPosition, PositionRois
from zml_ocr_agent.pipelines.position.preprocess import (
    DigitsPreprocessConfig,
    DigitsPreprocessor,
)
from zml_ocr_agent.pipelines.text import digits_only
from zml_ocr_agent.profiling import OcrProfiler


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
        profiler: OcrProfiler | None = None,
    ) -> None:
        self._rois = rois
        self._engine = engine or TesserDigitsEngine()
        self._pre_cfg = pre_cfg or DigitsPreprocessConfig()
        self._pre = DigitsPreprocessor(pre_cfg)
        self._cfg = cfg or PositionPipelineConfig()
        self._profiler = profiler

        self._last_emitted: tuple[int, int] | None = None

    def close(self) -> None:
        self._engine.close()

    def step(self, compass_roi: np.ndarray, ts_ms: int) -> OcrPosition | None:
        with self._measure("position.step"):
            with self._measure("position.crop"):
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
                position=WorldPosition(
                    planet_name="",  # fill later when planet OCR returns
                    x=lon,
                    y=lat,
                    z=None,
                ),
            )

    def _read_int(self, img: np.ndarray) -> int | None:
        with self._measure("position.preprocess"):
            pre = self._pre.process(img)
        with self._measure("position.ocr"):
            raw = self._engine.recognize_digits(pre)

        with self._measure("position.parse"):
            digits = digits_only(raw)
            if not digits:
                return None

            try:
                val = int(digits)
            except ValueError:
                return None

            if not (self._cfg.sanity_min <= val <= self._cfg.sanity_max):
                return None

            return val

    def _measure(self, name: str):
        if self._profiler is None:
            return _NullMeasure()
        return self._profiler.measure(name)


class _NullMeasure:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *args: object) -> None:
        return None
