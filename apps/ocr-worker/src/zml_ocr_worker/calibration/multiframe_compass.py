from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from statistics import median

import numpy as np

from zml_ocr_worker.calibration.compass import CompassLocator, CompassLocatorConfig
from zml_ocr_worker.calibration.model import LocatedCompass
from zml_ocr_worker.capture.model import RoiRect


@dataclass(frozen=True, slots=True)
class MultiFrameCompassLocatorConfig:
    sample_count: int = 7
    min_inliers: int = 5
    center_tolerance_radius_fraction: float = 0.08
    radius_tolerance_fraction: float = 0.08


class MultiFrameCompassLocator(CompassLocator):
    """Require a stable Compass consensus across several consecutive frames."""

    def __init__(
        self,
        *,
        locator_config: CompassLocatorConfig | None = None,
        config: MultiFrameCompassLocatorConfig | None = None,
    ) -> None:
        super().__init__(config=locator_config)
        self._multi_config = config or MultiFrameCompassLocatorConfig()
        self._samples: list[LocatedCompass] = []

    @property
    def acquiring(self) -> bool:
        return bool(self._samples)

    def locate(self, frame: np.ndarray) -> LocatedCompass | None:
        candidate = self._locate_single(frame)
        if candidate is None:
            self._samples.clear()
            return None

        self._samples.append(candidate)
        sample_count = max(1, self._multi_config.sample_count)
        if len(self._samples) < sample_count:
            return None

        samples = self._samples[-sample_count:]
        self._samples.clear()
        consensus = _consensus_compass(samples, config=self._multi_config)
        if consensus is None:
            return None

        # CompassLocator intentionally tolerates one failed locked validation.
        # Require two checks before accepting a newly aggregated calibration.
        if not self.locked_is_valid(frame, consensus) or not self.locked_is_valid(frame, consensus):
            return None
        return consensus

    def _locate_single(self, frame: np.ndarray) -> LocatedCompass | None:
        return super().locate(frame)


def _consensus_compass(
    samples: list[LocatedCompass],
    *,
    config: MultiFrameCompassLocatorConfig,
) -> LocatedCompass | None:
    if not samples:
        return None

    median_center_x = float(median(sample.center_x for sample in samples))
    median_center_y = float(median(sample.center_y for sample in samples))
    median_radius = float(median(sample.radius for sample in samples))
    center_tolerance = max(3.0, median_radius * config.center_tolerance_radius_fraction)
    radius_tolerance = max(2.0, median_radius * config.radius_tolerance_fraction)

    inliers = [
        sample
        for sample in samples
        if hypot(sample.center_x - median_center_x, sample.center_y - median_center_y)
        <= center_tolerance
        and abs(sample.radius - median_radius) <= radius_tolerance
    ]
    min_inliers = min(max(1, config.min_inliers), max(1, config.sample_count))
    if len(inliers) < min_inliers:
        return None

    x1 = round(median(sample.rect.x1 for sample in inliers))
    x2 = round(median(sample.rect.x2 for sample in inliers))
    y1 = round(median(sample.rect.y1 for sample in inliers))
    y2 = round(median(sample.rect.y2 for sample in inliers))
    if x2 <= x1 or y2 <= y1:
        return None

    return LocatedCompass(
        rect=RoiRect(x1=x1, x2=x2, y1=y1, y2=y2),
        confidence=float(median(sample.confidence for sample in inliers)),
        scale=float(median(sample.scale for sample in inliers)),
        center_x=float(median(sample.center_x for sample in inliers)),
        center_y=float(median(sample.center_y for sample in inliers)),
        radius=float(median(sample.radius for sample in inliers)),
    )
