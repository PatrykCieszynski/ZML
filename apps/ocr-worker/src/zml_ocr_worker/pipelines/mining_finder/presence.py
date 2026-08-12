from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from zml_ocr_worker.pipelines.image import RelativeRect, to_bgr_u8, to_gray_u8


@dataclass(frozen=True, slots=True)
class FinderPresenceConfig:
    min_score: float = 0.55
    min_panel_dark_score: float = 0.55
    min_grid_score: float = 0.20
    min_blue_score: float = 0.15
    min_radar_ring_score: float = 0.45
    panel_dark_threshold: int = 70
    radar_center_x: float = 0.26
    radar_center_y: float = 0.36
    radar_radii: tuple[float, ...] = (0.085, 0.145, 0.215)
    radar_band_fraction: float = 0.018
    radar_sector_count: int = 48


@dataclass(frozen=True, slots=True)
class FinderPresenceResult:
    present: bool
    score: float
    panel_dark_score: float
    grid_score: float
    blue_score: float
    green_score: float
    radar_ring_score: float


class FinderPresenceDetector:
    """Cheap visual guard that skips expensive OCR when the finder panel is not visible."""

    def __init__(self, *, config: FinderPresenceConfig | None = None) -> None:
        self._config = config or FinderPresenceConfig()

    def detect(self, finder_roi: np.ndarray) -> FinderPresenceResult:
        if finder_roi.size == 0 or finder_roi.shape[0] < 40 or finder_roi.shape[1] < 80:
            return FinderPresenceResult(
                present=False,
                score=0.0,
                panel_dark_score=0.0,
                grid_score=0.0,
                blue_score=0.0,
                green_score=0.0,
                radar_ring_score=0.0,
            )

        gray = to_gray_u8(finder_roi)
        bgr = to_bgr_u8(finder_roi)
        panel_dark_score = self._panel_dark_score(gray)
        grid_score = self._grid_score(gray)
        blue, green = self._color_masks(bgr)
        blue_score, green_score = self._color_scores(blue, green)
        radar_ring_score = self._radar_ring_score(blue)
        score = (
            panel_dark_score * 0.35
            + grid_score * 0.25
            + blue_score * 0.15
            + green_score * 0.05
            + radar_ring_score * 0.20
        )
        present = (
            score >= self._config.min_score
            and panel_dark_score >= self._config.min_panel_dark_score
            and grid_score >= self._config.min_grid_score
            and blue_score >= self._config.min_blue_score
            and radar_ring_score >= self._config.min_radar_ring_score
        )
        return FinderPresenceResult(
            present=present,
            score=score,
            panel_dark_score=panel_dark_score,
            grid_score=grid_score,
            blue_score=blue_score,
            green_score=green_score,
            radar_ring_score=radar_ring_score,
        )

    def _panel_dark_score(self, gray: np.ndarray) -> float:
        panel_rects: tuple[RelativeRect, ...] = (
            (0.05, 0.05, 0.45, 0.68),
            (0.52, 0.05, 0.96, 0.32),
            (0.52, 0.39, 0.96, 0.68),
            (0.52, 0.74, 0.96, 0.96),
        )
        scores = [
            _dark_ratio(_crop_relative(gray, rect), self._config.panel_dark_threshold)
            for rect in panel_rects
        ]
        return float(sum(scores) / len(scores))

    def _grid_score(self, gray: np.ndarray) -> float:
        edges = cv2.Canny(gray, 40, 120) > 0
        line_specs: tuple[tuple[RelativeRect, RelativeRect, RelativeRect], ...] = (
            (
                (0.47, 0.02, 0.51, 0.98),
                (0.41, 0.02, 0.45, 0.98),
                (0.53, 0.02, 0.57, 0.98),
            ),
            (
                (0.01, 0.68, 0.49, 0.72),
                (0.01, 0.60, 0.49, 0.64),
                (0.01, 0.76, 0.49, 0.80),
            ),
            (
                (0.50, 0.33, 0.99, 0.37),
                (0.50, 0.25, 0.99, 0.29),
                (0.50, 0.43, 0.99, 0.47),
            ),
            (
                (0.50, 0.70, 0.99, 0.74),
                (0.50, 0.62, 0.99, 0.66),
                (0.50, 0.80, 0.99, 0.84),
            ),
        )
        normalized: list[float] = []
        for line_rect, before_rect, after_rect in line_specs:
            line_density = _edge_density(_crop_relative(edges, line_rect))
            neighbor_density = (
                _edge_density(_crop_relative(edges, before_rect))
                + _edge_density(_crop_relative(edges, after_rect))
            ) / 2.0
            normalized.append(min(max(line_density - neighbor_density, 0.0) / 0.08, 1.0))
        return float(sum(normalized) / len(normalized))

    def _color_masks(self, bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        hue = hsv[:, :, 0]
        sat = hsv[:, :, 1]
        val = hsv[:, :, 2]
        blue = (hue >= 85) & (hue <= 130) & (sat >= 60) & (val >= 50)
        green = (hue >= 45) & (hue <= 80) & (sat >= 70) & (val >= 70)
        return blue, green

    def _color_scores(self, blue: np.ndarray, green: np.ndarray) -> tuple[float, float]:
        blue_score = min(float(np.count_nonzero(blue)) / float(blue.size) / 0.025, 1.0)
        green_score = min(float(np.count_nonzero(green)) / float(green.size) / 0.035, 1.0)
        return blue_score, green_score

    def _radar_ring_score(self, blue: np.ndarray) -> float:
        """Score the three blue concentric radar rings in the Finders upper-left panel.

        Generic Entropia windows can look dark and contain blue/green UI pixels, but
        the Finder has a much stronger invariant: three large blue rings at fixed
        normalized positions. Measure angular coverage rather than raw blue density
        so isolated inventory icons cannot satisfy the guard accidentally.
        """

        height = int(blue.shape[0])
        width = int(blue.shape[1])
        scale = float(min(width, height))
        center_x = self._config.radar_center_x * width
        center_y = self._config.radar_center_y * height
        band = max(1.0, self._config.radar_band_fraction * scale)
        sector_count = max(12, int(self._config.radar_sector_count))
        angles = np.linspace(0.0, 2.0 * np.pi, sector_count, endpoint=False)
        cos_angles = np.cos(angles)
        sin_angles = np.sin(angles)

        # Expand each blue pixel by one pixel once, instead of running hundreds of
        # tiny np.any slices from Python. Sampling the three radial bands then becomes
        # pure vectorized indexing and keeps the locked-presence hot path cheap.
        expanded = cv2.dilate(blue.astype(np.uint8), np.ones((3, 3), dtype=np.uint8)) > 0
        radial_offsets = np.asarray((-band, 0.0, band), dtype=np.float64)[:, None]

        ring_scores: list[float] = []
        for radius_fraction in self._config.radar_radii:
            radius = max(1.0, radius_fraction * scale)
            sample_radii = radius + radial_offsets
            xs = np.rint(center_x + sample_radii * cos_angles[None, :]).astype(np.int32)
            ys = np.rint(center_y + sample_radii * sin_angles[None, :]).astype(np.int32)
            valid = (xs >= 0) & (xs < width) & (ys >= 0) & (ys < height)
            sampled = np.zeros_like(valid, dtype=bool)
            sampled[valid] = expanded[ys[valid], xs[valid]]
            sector_hits = np.any(sampled, axis=0)
            ring_scores.append(float(np.count_nonzero(sector_hits)) / float(sector_count))

        if not ring_scores:
            return 0.0
        return float(sum(ring_scores) / len(ring_scores))


def _crop_relative(img: np.ndarray, rect: RelativeRect) -> np.ndarray:
    height = int(img.shape[0])
    width = int(img.shape[1])
    x1 = max(0, min(width, int(width * rect[0])))
    y1 = max(0, min(height, int(height * rect[1])))
    x2 = max(0, min(width, int(width * rect[2])))
    y2 = max(0, min(height, int(height * rect[3])))
    if x2 <= x1 or y2 <= y1:
        return np.zeros((1, 1), dtype=img.dtype)
    return np.ascontiguousarray(img[y1:y2, x1:x2])


def _dark_ratio(gray: np.ndarray, threshold: int) -> float:
    if gray.size == 0:
        return 0.0
    return float(np.count_nonzero(gray <= threshold)) / float(gray.size)


def _edge_density(edge_mask: np.ndarray) -> float:
    if edge_mask.size == 0:
        return 0.0
    return float(np.count_nonzero(edge_mask)) / float(edge_mask.size)
