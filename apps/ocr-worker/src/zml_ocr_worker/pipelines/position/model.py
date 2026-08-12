from dataclasses import dataclass

from zml_ocr_worker.capture.model import RoiRect
from zml_ocr_worker.pipelines.model import WorldPosition


@dataclass(frozen=True, slots=True)
class OcrPosition:
    ts_ms: int
    position: WorldPosition


@dataclass(frozen=True, slots=True)
class CoordinateRois:
    lon: RoiRect
    lat: RoiRect
    extract_numeric_tokens: bool = False


@dataclass(frozen=True, slots=True)
class PositionRois:
    # All coords are relative to the compass ROI (not the full screen).
    planet: RoiRect
    lon: RoiRect
    lat: RoiRect

    def coordinates(self) -> CoordinateRois:
        return CoordinateRois(lon=self.lon, lat=self.lat)
