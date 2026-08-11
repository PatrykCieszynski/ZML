from __future__ import annotations

from dataclasses import dataclass

from zml_ocr_worker.calibration.model import LocatedCompass
from zml_ocr_worker.capture.model import RoiRect
from zml_ocr_worker.pipelines.position.model import CoordinateRois


@dataclass(frozen=True, slots=True)
class CompassCoordinateLayoutConfig:
    # Ratios are relative to the detected radar center/radius, not the outer crop.
    # Lon/Lat are rendered as complete right-aligned strings, so one fixed line ROI
    # can cover both the label and every supported coordinate length.
    line_left_radius: float = -1.02
    line_right_radius: float = -0.14
    # Live calibration showed that the earlier nominal lines were about 0.06r too
    # high. The UI keeps the coordinate rows at a fixed radar-relative position, so
    # bake the observed offset into the deterministic geometry instead of probing
    # several vertical OCR layouts at runtime.
    longitude_top_radius: float = 1.03
    longitude_bottom_radius: float = 1.18
    latitude_top_radius: float = 1.21
    latitude_bottom_radius: float = 1.36


class CompassCoordinateLayout:
    """Derive scale-aware fixed Lon/Lat line ROIs from a located Compass.

    This class deliberately does no OCR. The detected radar center/radius is the
    calibration anchor, so moving or resizing the Compass automatically moves and
    scales these lines without trying alternative OCR positions.
    """

    def __init__(self, *, config: CompassCoordinateLayoutConfig | None = None) -> None:
        self._config = config or CompassCoordinateLayoutConfig()

    def rois(self, compass: LocatedCompass) -> CoordinateRois:
        return CoordinateRois(
            lon=_local_rect_from_radar(
                compass,
                left_radius=self._config.line_left_radius,
                right_radius=self._config.line_right_radius,
                top_radius=self._config.longitude_top_radius,
                bottom_radius=self._config.longitude_bottom_radius,
            ),
            lat=_local_rect_from_radar(
                compass,
                left_radius=self._config.line_left_radius,
                right_radius=self._config.line_right_radius,
                top_radius=self._config.latitude_top_radius,
                bottom_radius=self._config.latitude_bottom_radius,
            ),
            extract_numeric_tokens=True,
        )


def _local_rect_from_radar(
    compass: LocatedCompass,
    *,
    left_radius: float,
    right_radius: float,
    top_radius: float,
    bottom_radius: float,
) -> RoiRect:
    crop_width = compass.rect.x2 - compass.rect.x1
    crop_height = compass.rect.y2 - compass.rect.y1
    radius = compass.radius

    x1 = round(compass.center_x + radius * left_radius) - compass.rect.x1
    x2 = round(compass.center_x + radius * right_radius) - compass.rect.x1
    y1 = round(compass.center_y + radius * top_radius) - compass.rect.y1
    y2 = round(compass.center_y + radius * bottom_radius) - compass.rect.y1

    x1 = max(0, min(crop_width, x1))
    x2 = max(0, min(crop_width, x2))
    y1 = max(0, min(crop_height, y1))
    y2 = max(0, min(crop_height, y2))
    return RoiRect(x1=x1, x2=x2, y1=y1, y2=y2)
