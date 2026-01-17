from dataclasses import dataclass

from zml_game_bridge.common.models import WorldPos
from zml_game_bridge.inputs.ocr.capture.model import RoiRect


@dataclass(frozen=True, slots=True)
class OcrPosition:
    ts_ms: int
    position: WorldPos

@dataclass(frozen=True, slots=True)
class PositionRois:
    # All coords are relative to the compass ROI (not the full screen).
    planet: RoiRect
    lon: RoiRect
    lat: RoiRect