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
    longitude_top_radius: float = 0.94
    longitude_bottom_radius: float = 1.14
    latitude_top_radius: float = 1.10
    latitude_bottom_radius: float = 1.32
    vertical_offset_candidates: tuple[float, ...] = (0.0, -0.03, 0.03, -0.06, 0.06)


@dataclass(frozen=True, slots=True)
class CompassCoordinateLayoutVariant:
    vertical_offset_radius: float
    rois: CoordinateRois


class CompassCoordinateLayout:
    """Derive scale-aware fixed Lon/Lat line ROIs from a located Compass.

    This class deliberately does no OCR. Each ROI contains the complete right-aligned
    coordinate line. The PositionPipeline cheaply extracts the rightmost numeric token
    before invoking its existing digits-only Tesseract engine.
    """

    def __init__(self, *, config: CompassCoordinateLayoutConfig | None = None) -> None:
        self._config = config or CompassCoordinateLayoutConfig()

    def variants(self, compass: LocatedCompass) -> tuple[CompassCoordinateLayoutVariant, ...]:
        return tuple(
            CompassCoordinateLayoutVariant(
                vertical_offset_radius=vertical_offset,
                rois=self._coordinate_rois(
                    compass,
                    vertical_offset=vertical_offset,
                ),
            )
            for vertical_offset in self._config.vertical_offset_candidates
        )

    def _coordinate_rois(
        self,
        compass: LocatedCompass,
        *,
        vertical_offset: float,
    ) -> CoordinateRois:
        return CoordinateRois(
            lon=_local_rect_from_radar(
                compass,
                left_radius=self._config.line_left_radius,
                right_radius=self._config.line_right_radius,
                top_radius=self._config.longitude_top_radius + vertical_offset,
                bottom_radius=self._config.longitude_bottom_radius + vertical_offset,
            ),
            lat=_local_rect_from_radar(
                compass,
                left_radius=self._config.line_left_radius,
                right_radius=self._config.line_right_radius,
                top_radius=self._config.latitude_top_radius + vertical_offset,
                bottom_radius=self._config.latitude_bottom_radius + vertical_offset,
            ),
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
