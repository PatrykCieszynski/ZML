from __future__ import annotations

from dataclasses import dataclass

from zml_ocr_worker.calibration.model import LocatedCompass
from zml_ocr_worker.capture.model import RoiRect
from zml_ocr_worker.pipelines.position.model import CoordinateRois


@dataclass(frozen=True, slots=True)
class CompassCoordinateLayoutConfig:
    # Ratios are relative to the detected radar center/radius, not the outer crop.
    # Community screenshots show that the Lon/Lat block can move horizontally
    # relative to the radar while its vertical rows remain stable. Cover the full
    # useful X range and let occasional text OCR locate the value word inside each
    # strip instead of predicting the coordinate block's X position.
    line_left_radius: float = -1.22
    line_right_radius: float = 0.15

    # Live and community calibration put the row centers at roughly 1.10r / 1.29r
    # below the radar center. A small symmetric vertical margin absorbs rounding
    # and anti-aliasing differences without probing alternate Y layouts.
    longitude_center_radius: float = 1.10
    latitude_center_radius: float = 1.29
    line_half_height_radius: float = 0.09


@dataclass(frozen=True, slots=True)
class CompassCoordinateLayoutVariant:
    vertical_offset_radius: float
    rois: CoordinateRois


class CompassCoordinateLayout:
    """Derive one scale-aware Lon/Lat text-search strip pair from a Compass.

    The radar center/radius determines Y and scale. X is intentionally wider
    because the coordinate block is not at one stable radar-relative horizontal
    offset across observed Entropia UI variants. CoordinateTextCalibrator uses the
    strips only when calibration/recovery is needed; normal position OCR uses the
    exact cached digit boxes produced by that calibration.
    """

    def __init__(self, *, config: CompassCoordinateLayoutConfig | None = None) -> None:
        self._config = config or CompassCoordinateLayoutConfig()

    def variants(self, compass: LocatedCompass) -> tuple[CompassCoordinateLayoutVariant, ...]:
        # Keep the variant wrapper for the runtime interface, but there is now only
        # one deterministic Y layout. OCR failures no longer cause vertical probing.
        return (
            CompassCoordinateLayoutVariant(
                vertical_offset_radius=0.0,
                rois=self._coordinate_rois(compass),
            ),
        )

    def _coordinate_rois(self, compass: LocatedCompass) -> CoordinateRois:
        half_height = self._config.line_half_height_radius
        return CoordinateRois(
            lon=_local_rect_from_radar(
                compass,
                left_radius=self._config.line_left_radius,
                right_radius=self._config.line_right_radius,
                top_radius=self._config.longitude_center_radius - half_height,
                bottom_radius=self._config.longitude_center_radius + half_height,
            ),
            lat=_local_rect_from_radar(
                compass,
                left_radius=self._config.line_left_radius,
                right_radius=self._config.line_right_radius,
                top_radius=self._config.latitude_center_radius - half_height,
                bottom_radius=self._config.latitude_center_radius + half_height,
            ),
            extract_numeric_tokens=False,
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
