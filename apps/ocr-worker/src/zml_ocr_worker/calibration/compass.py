from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from zml_ocr_worker.calibration.model import LocatedCompass
from zml_ocr_worker.capture.model import RoiRect


@dataclass(frozen=True, slots=True)
class CompassLocatorConfig:
    search_max_width: int = 1280
    min_radius_fraction: float = 0.04
    max_radius_fraction: float = 0.18
    hough_dp: float = 1.2
    hough_param1: float = 120.0
    hough_param2: float = 30.0
    min_ring_contrast: float = 0.65
    baseline_radius: float = 142.0
    left_radius_factor: float = 1.22
    top_radius_factor: float = 1.49
    width_radius_factor: float = 2.57
    # The old known-good 2560x1440 Compass crop was 446 px tall at ~142 px
    # radar radius. Keep the extra area below the radar so Lat and recovery
    # offsets are never clipped by the discovered outer rectangle.
    height_radius_factor: float = 3.14
    locked_validation_min_score: float = 0.55


class CompassLocator:
    """Locate the movable/resizable Compass from its concentric radar rings."""

    def __init__(self, *, config: CompassLocatorConfig | None = None) -> None:
        self._config = config or CompassLocatorConfig()

    def locate(self, frame: np.ndarray) -> LocatedCompass | None:
        if frame.size == 0 or frame.ndim != 3:
            return None

        search_frame, search_scale = self._search_frame(frame)
        gray = cv2.cvtColor(search_frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 1.2)
        min_dimension = min(int(gray.shape[0]), int(gray.shape[1]))
        min_radius = max(12, round(min_dimension * self._config.min_radius_fraction))
        max_radius = max(min_radius + 1, round(min_dimension * self._config.max_radius_fraction))

        circles = cv2.HoughCircles(
            blurred,
            cv2.HOUGH_GRADIENT,
            dp=self._config.hough_dp,
            minDist=max(16.0, float(min_radius) * 0.45),
            param1=self._config.hough_param1,
            param2=self._config.hough_param2,
            minRadius=min_radius,
            maxRadius=max_radius,
        )
        if circles is None:
            return None

        edges = cv2.Canny(gray, 50, 140) > 0
        best_circle: tuple[float, float, float] | None = None
        best_score = float("-inf")
        for raw_circle in circles[0]:
            circle = (float(raw_circle[0]), float(raw_circle[1]), float(raw_circle[2]))
            score = _ring_contrast(edges, circle)
            if score > best_score:
                best_score = score
                best_circle = circle

        if best_circle is None or best_score < self._config.min_ring_contrast:
            return None

        inverse_scale = 1.0 / search_scale
        center_x = best_circle[0] * inverse_scale
        center_y = best_circle[1] * inverse_scale
        radius = best_circle[2] * inverse_scale
        rect = self._outer_rect(
            frame_width=int(frame.shape[1]),
            frame_height=int(frame.shape[0]),
            center_x=center_x,
            center_y=center_y,
            radius=radius,
        )
        return LocatedCompass(
            rect=rect,
            confidence=min(max(best_score, 0.0), 1.0),
            scale=radius / self._config.baseline_radius,
            center_x=center_x,
            center_y=center_y,
            radius=radius,
        )

    def validate_locked(self, frame: np.ndarray, compass: LocatedCompass) -> float:
        """Cheaply validate the already-known radar without running Hough again."""
        if frame.size == 0 or frame.ndim != 3:
            return 0.0
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 140) > 0
        score = _ring_contrast(
            edges,
            (compass.center_x, compass.center_y, compass.radius),
        )
        return float(min(max(score, 0.0), 1.0))

    def locked_is_valid(self, frame: np.ndarray, compass: LocatedCompass) -> bool:
        return self.validate_locked(frame, compass) >= self._config.locked_validation_min_score

    def _search_frame(self, frame: np.ndarray) -> tuple[np.ndarray, float]:
        frame_width = int(frame.shape[1])
        if frame_width <= self._config.search_max_width:
            return frame, 1.0
        scale = self._config.search_max_width / frame_width
        target_height = max(1, round(int(frame.shape[0]) * scale))
        resized = cv2.resize(
            frame,
            (self._config.search_max_width, target_height),
            interpolation=cv2.INTER_AREA,
        )
        return resized, scale

    def _outer_rect(
        self,
        *,
        frame_width: int,
        frame_height: int,
        center_x: float,
        center_y: float,
        radius: float,
    ) -> RoiRect:
        x1 = round(center_x - radius * self._config.left_radius_factor)
        y1 = round(center_y - radius * self._config.top_radius_factor)
        width = round(radius * self._config.width_radius_factor)
        height = round(radius * self._config.height_radius_factor)
        x1 = max(0, min(x1, frame_width - 1))
        y1 = max(0, min(y1, frame_height - 1))
        x2 = max(x1 + 1, min(frame_width, x1 + width))
        y2 = max(y1 + 1, min(frame_height, y1 + height))
        return RoiRect(x1=x1, x2=x2, y1=y1, y2=y2)


def _ring_contrast(
    edge_mask: np.ndarray,
    circle: tuple[float, float, float],
) -> float:
    center_x, center_y, radius = circle
    ring_fractions = (0.2, 0.4, 0.6, 0.8, 1.0)
    valley_fractions = (0.1, 0.3, 0.5, 0.7, 0.9)
    ring_support = sum(
        _circle_edge_support(edge_mask, center_x, center_y, radius * fraction)
        for fraction in ring_fractions
    ) / len(ring_fractions)
    valley_support = sum(
        _circle_edge_support(edge_mask, center_x, center_y, radius * fraction)
        for fraction in valley_fractions
    ) / len(valley_fractions)
    return float(ring_support - valley_support * 0.55)


def _circle_edge_support(
    edge_mask: np.ndarray,
    center_x: float,
    center_y: float,
    radius: float,
    *,
    samples: int = 120,
    tolerance_px: int = 1,
) -> float:
    height = int(edge_mask.shape[0])
    width = int(edge_mask.shape[1])
    hits = 0
    considered = 0
    for angle in np.linspace(0.0, np.pi * 2.0, samples, endpoint=False):
        x = round(center_x + radius * np.cos(angle))
        y = round(center_y + radius * np.sin(angle))
        if x < 0 or x >= width or y < 0 or y >= height:
            continue
        considered += 1
        x1 = max(0, x - tolerance_px)
        x2 = min(width, x + tolerance_px + 1)
        y1 = max(0, y - tolerance_px)
        y2 = min(height, y + tolerance_px + 1)
        if np.any(edge_mask[y1:y2, x1:x2]):
            hits += 1
    if considered == 0:
        return 0.0
    return hits / considered
