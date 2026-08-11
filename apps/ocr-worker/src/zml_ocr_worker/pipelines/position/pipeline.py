from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from zml_ocr_worker.pipelines.model import WorldPosition
from zml_ocr_worker.pipelines.position.engine import TesserDigitsEngine
from zml_ocr_worker.pipelines.position.model import CoordinateRois, OcrPosition, PositionRois
from zml_ocr_worker.pipelines.position.preprocess import (
    DigitsPreprocessConfig,
    DigitsPreprocessor,
)
from zml_ocr_worker.pipelines.text import digits_only
from zml_ocr_worker.runtime.profiling import OcrProfiler


@dataclass(frozen=True, slots=True)
class PositionPipelineConfig:
    sanity_min: int = 1000
    sanity_max: int = 10_000_000
    candidate_min_confidence: float = 0.35


@dataclass(frozen=True, slots=True)
class PositionReadResult:
    longitude: int | None
    latitude: int | None
    position: OcrPosition | None
    confidence: float | None = None

    @property
    def valid(self) -> bool:
        return self.longitude is not None and self.latitude is not None

    def is_healthy(self, *, min_confidence: float) -> bool:
        if not self.valid:
            return False
        return self.confidence is None or self.confidence >= min_confidence


class PositionPipeline:
    def __init__(
        self,
        rois: PositionRois | CoordinateRois,
        *,
        engine: TesserDigitsEngine | None = None,
        pre_cfg: DigitsPreprocessConfig | None = None,
        cfg: PositionPipelineConfig | None = None,
        profiler: OcrProfiler | None = None,
    ) -> None:
        self._rois = rois.coordinates() if isinstance(rois, PositionRois) else rois
        self._engine = engine or TesserDigitsEngine()
        self._pre_cfg = pre_cfg or DigitsPreprocessConfig()
        self._pre = DigitsPreprocessor(pre_cfg)
        self._cfg = cfg or PositionPipelineConfig()
        self._profiler = profiler

        self._last_emitted: tuple[int, int] | None = None

    def close(self) -> None:
        self._engine.close()

    def step(
        self,
        compass_roi: np.ndarray,
        ts_ms: int,
        *,
        rois: CoordinateRois | None = None,
    ) -> OcrPosition | None:
        return self.read(compass_roi, ts_ms, rois=rois).position

    def read(
        self,
        compass_roi: np.ndarray,
        ts_ms: int,
        *,
        rois: CoordinateRois | None = None,
        emit: bool = True,
    ) -> PositionReadResult:
        active_rois = rois or self._rois
        with self._measure("position.step"):
            with self._measure("position.crop"):
                lon_img = active_rois.lon.crop(compass_roi)
                lat_img = active_rois.lat.crop(compass_roi)

            if lon_img is None or lat_img is None:
                return PositionReadResult(longitude=None, latitude=None, position=None)

            lon, lon_confidence = self._read_int(lon_img)
            lat, lat_confidence = self._read_int(lat_img)
            confidence = _combined_confidence(lon_confidence, lat_confidence)
            result = PositionReadResult(
                longitude=lon,
                latitude=lat,
                position=None,
                confidence=confidence,
            )
            if not result.valid or not emit:
                return result
            return self._emit_position(result, ts_ms=ts_ms)

    def read_candidates(
        self,
        compass_roi: np.ndarray,
        ts_ms: int,
        roi_candidates: Sequence[CoordinateRois],
    ) -> PositionReadResult:
        last = PositionReadResult(longitude=None, latitude=None, position=None)
        for candidate in roi_candidates:
            last = self.read(compass_roi, ts_ms, rois=candidate, emit=False)
            if last.is_healthy(min_confidence=self._cfg.candidate_min_confidence):
                return self._emit_position(last, ts_ms=ts_ms)
        return last

    def _emit_position(self, read: PositionReadResult, *, ts_ms: int) -> PositionReadResult:
        if not read.valid:
            return read
        lon = read.longitude
        lat = read.latitude
        if lon is None or lat is None:
            return read
        if (lon, lat) == self._last_emitted:
            return read

        self._last_emitted = (lon, lat)
        return PositionReadResult(
            longitude=lon,
            latitude=lat,
            position=OcrPosition(
                ts_ms=ts_ms,
                position=WorldPosition(
                    planet_name="",  # fill later when planet OCR returns
                    x=lon,
                    y=lat,
                    z=None,
                ),
            ),
            confidence=read.confidence,
        )

    def _read_int(self, img: np.ndarray) -> tuple[int | None, float | None]:
        with self._measure("position.preprocess"):
            pre = self._pre.process(img)
        with self._measure("position.ocr"):
            raw = self._engine.recognize_digits(pre)
            confidence = _last_engine_confidence(self._engine)

        with self._measure("position.parse"):
            digits = digits_only(raw)
            if not digits:
                return None, confidence

            try:
                val = int(digits)
            except ValueError:
                return None, confidence

            if not (self._cfg.sanity_min <= val <= self._cfg.sanity_max):
                return None, confidence

            return val, confidence

    def _measure(self, name: str):
        if self._profiler is None:
            return _NullMeasure()
        return self._profiler.measure(name)


class _NullMeasure:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *args: object) -> None:
        return None


def _last_engine_confidence(engine: object) -> float | None:
    value = getattr(engine, "last_confidence", None)
    if isinstance(value, int | float):
        return min(max(float(value), 0.0), 1.0)
    return None


def _combined_confidence(*values: float | None) -> float | None:
    available = [value for value in values if value is not None]
    return min(available) if available else None
