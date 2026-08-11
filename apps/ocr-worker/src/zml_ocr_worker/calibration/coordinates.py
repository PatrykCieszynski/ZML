from __future__ import annotations

from dataclasses import dataclass

from zml_ocr_worker.calibration.model import LocatedCompass
from zml_ocr_worker.capture.model import RoiRect
from zml_ocr_worker.pipelines.position.model import CoordinateRois


@dataclass(frozen=True, slots=True)
class CompassCoordinateLayoutConfig:
    # Ratios are relative to the detected radar center/radius, not the outer crop.
    # The defaults are derived from the existing known-good MVP Lon/Lat pixel ROIs.
    longitude_left_radius: float = -0.64
    latitude_left_radius: float = -0.60
    right_radius_candidates: tuple[float, ...] = (-0.18, -0.02, 0.14)
    longitude_top_radius: float = 0.94
    longitude_bottom_radius: float = 1.14
    latitude_top_radius: float = 1.10
    latitude_bottom_radius: float = 1.32
    vertical_offset_candidates: tuple[float, ...] = (0.0, -0.03, 0.03, -0.06, 0.06)


@dataclass(frozen=True, slots=True)
class CompassCoordinateLayoutVariant:
    vertical_offset_radius: float
    roi_candidates: tuple[CoordinateRois, ...]


class CompassCoordinateLayout:
    """Derive scale-aware Lon/Lat digit ROIs from a located Compass.

    This class deliberately does no OCR. It only tells the existing PositionPipeline
    where to look. Each vertical variant contains progressively wider digit strips so
    the pipeline can handle planets with shorter or longer coordinate values without
    scanning an arbitrary text block.
    """

    def __init__(self, *, config: CompassCoordinateLayoutConfig | None = None) -> None:
        self._config = config or CompassCoordinateLayoutConfig()

    def variants(self, compass: LocatedCompass) -> tuple[CompassCoordinateLayoutVariant, ...]:
        variants: list[CompassCoordinateLayoutVariant] = []
        for vertical_offset in self._config.vertical_offset_candidates:
            roi_candidates = tuple(
                self._coordinate_rois(
                    compass,
                    right_radius=right_radius,
                    vertical_offset=vertical_offset,
                )
                for right_radius in self._config.right_radius_candidates
            )
            variants.append(
                CompassCoordinateLayoutVariant(
                    vertical_offset_radius=vertical_offset,
                    roi_candidates=roi_candidates,
                )
            )
        return tuple(variants)

    def _coordinate_rois(
        self,
        compass: LocatedCompass,
        *,
        right_radius: float,
        vertical_offset: float,
    ) -> CoordinateRois:
        return CoordinateRois(
            lon=_local_rect_from_radar(
                compass,
                left_radius=self._config.longitude_left_radius,
                right_radius=right_radius,
                top_radius=self._config.longitude_top_radius + vertical_offset,
                bottom_radius=self._config.longitude_bottom_radius + vertical_offset,
            ),
            lat=_local_rect_from_radar(
                compass,
                left_radius=self._config.latitude_left_radius,
                right_radius=right_radius,
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
