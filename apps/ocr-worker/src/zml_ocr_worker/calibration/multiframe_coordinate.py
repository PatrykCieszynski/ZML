from __future__ import annotations

from dataclasses import dataclass
from statistics import median

import numpy as np

from zml_ocr_worker.calibration.coordinate_ocr import (
    CoordinateCalibration,
    CoordinateTextCalibrator,
)
from zml_ocr_worker.capture.model import RoiRect
from zml_ocr_worker.pipelines.position.model import CoordinateRois


@dataclass(frozen=True, slots=True)
class MultiFrameCoordinateTextCalibratorConfig:
    sample_count: int = 5
    min_inliers: int = 4
    edge_tolerance_px: int = 4


class MultiFrameCoordinateTextCalibrator:
    """Require stable Lon/Lat value boxes across consecutive frames."""

    def __init__(
        self,
        *,
        calibrator: CoordinateTextCalibrator | None = None,
        config: MultiFrameCoordinateTextCalibratorConfig | None = None,
    ) -> None:
        self._calibrator = calibrator or CoordinateTextCalibrator()
        self._config = config or MultiFrameCoordinateTextCalibratorConfig()
        self._samples: list[CoordinateCalibration] = []

    @property
    def acquiring(self) -> bool:
        return bool(self._samples)

    def reset(self) -> None:
        self._samples.clear()

    def calibrate(
        self,
        compass_roi: np.ndarray,
        *,
        search_rois: CoordinateRois,
    ) -> CoordinateCalibration | None:
        try:
            candidate = self._calibrator.calibrate(
                compass_roi,
                search_rois=search_rois,
            )
        except Exception:
            self.reset()
            raise

        if candidate is None:
            self.reset()
            return None

        self._samples.append(candidate)
        sample_count = max(1, self._config.sample_count)
        if len(self._samples) < sample_count:
            return None

        samples = self._samples[-sample_count:]
        self.reset()
        return _consensus_coordinate_calibration(samples, config=self._config)

    def close(self) -> None:
        self._calibrator.close()


def _consensus_coordinate_calibration(
    samples: list[CoordinateCalibration],
    *,
    config: MultiFrameCoordinateTextCalibratorConfig,
) -> CoordinateCalibration | None:
    if not samples:
        return None

    median_lon = _median_rect([sample.rois.lon for sample in samples])
    median_lat = _median_rect([sample.rois.lat for sample in samples])
    tolerance = max(0, config.edge_tolerance_px)

    inliers = [
        sample
        for sample in samples
        if _rect_is_close(sample.rois.lon, median_lon, tolerance=tolerance)
        and _rect_is_close(sample.rois.lat, median_lat, tolerance=tolerance)
    ]
    min_inliers = min(max(1, config.min_inliers), max(1, config.sample_count))
    if len(inliers) < min_inliers:
        return None

    lon = _median_rect([sample.rois.lon for sample in inliers])
    lat = _median_rect([sample.rois.lat for sample in inliers])
    if lon.x2 <= lon.x1 or lon.y2 <= lon.y1 or lat.x2 <= lat.x1 or lat.y2 <= lat.y1:
        return None

    extract_numeric_tokens = inliers[0].rois.extract_numeric_tokens
    if any(sample.rois.extract_numeric_tokens != extract_numeric_tokens for sample in inliers):
        return None

    return CoordinateCalibration(
        rois=CoordinateRois(
            lon=lon,
            lat=lat,
            extract_numeric_tokens=extract_numeric_tokens,
        )
    )


def _median_rect(rects: list[RoiRect]) -> RoiRect:
    return RoiRect(
        x1=round(median(rect.x1 for rect in rects)),
        x2=round(median(rect.x2 for rect in rects)),
        y1=round(median(rect.y1 for rect in rects)),
        y2=round(median(rect.y2 for rect in rects)),
    )


def _rect_is_close(rect: RoiRect, expected: RoiRect, *, tolerance: int) -> bool:
    return all(
        abs(observed - target) <= tolerance
        for observed, target in (
            (rect.x1, expected.x1),
            (rect.x2, expected.x2),
            (rect.y1, expected.y1),
            (rect.y2, expected.y2),
        )
    )
