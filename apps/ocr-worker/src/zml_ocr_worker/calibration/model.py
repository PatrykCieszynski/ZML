from __future__ import annotations

from dataclasses import dataclass

from zml_ocr_worker.capture.model import RoiRect


@dataclass(frozen=True, slots=True)
class LocatedRegion:
    rect: RoiRect
    confidence: float
    scale: float


@dataclass(frozen=True, slots=True)
class LocatedCompass(LocatedRegion):
    center_x: float
    center_y: float
    radius: float
