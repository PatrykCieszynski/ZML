from dataclasses import dataclass

from zml_ocr_agent.capture.model import RoiRect
from zml_ocr_agent.pipelines.model import WorldPosition


@dataclass(frozen=True, slots=True)
class OcrPosition:
    ts_ms: int
    position: WorldPosition


@dataclass(frozen=True, slots=True)
class PositionRois:
    # All coords are relative to the compass ROI (not the full screen).
    planet: RoiRect
    lon: RoiRect
    lat: RoiRect
