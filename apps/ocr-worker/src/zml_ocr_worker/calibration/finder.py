from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from zml_ocr_worker.calibration.model import LocatedRegion
from zml_ocr_worker.capture.model import RoiRect
from zml_ocr_worker.pipelines.mining_finder.presence import FinderPresenceDetector


@dataclass(frozen=True, slots=True)
class FinderLocatorConfig:
    baseline_client_width: int = 2560
    baseline_client_height: int = 1440
    baseline_finder_width: int = 347
    baseline_finder_height: int = 239
    scale_tolerance: tuple[float, ...] = (0.98, 1.0, 1.02)
    coarse_stride_fraction: float = 0.08
    coarse_candidate_count: int = 6
    min_confidence: float = 0.68


@dataclass(frozen=True, slots=True)
class _Candidate:
    x: int
    y: int
    width: int
    height: int
    scale: float
    score: float
    presence: bool


class FinderLocator:
    """Locate the movable Entropia finder at the size implied by client resolution."""

    def __init__(
        self,
        *,
        config: FinderLocatorConfig | None = None,
        presence_detector: FinderPresenceDetector | None = None,
    ) -> None:
        self._config = config or FinderLocatorConfig()
        self._presence_detector = presence_detector or FinderPresenceDetector()

    def locate(self, frame: np.ndarray) -> LocatedRegion | None:
        if frame.size == 0 or frame.ndim != 3:
            return None

        frame_height = int(frame.shape[0])
        frame_width = int(frame.shape[1])
        base_scale = min(
            frame_width / self._config.baseline_client_width,
            frame_height / self._config.baseline_client_height,
        )
        if base_scale <= 0:
            return None

        best: _Candidate | None = None
        for tolerance in self._config.scale_tolerance:
            scale = base_scale * tolerance
            width = max(80, round(self._config.baseline_finder_width * scale))
            height = max(50, round(self._config.baseline_finder_height * scale))
            if width > frame_width or height > frame_height:
                continue
            candidate = self._locate_size(frame, width=width, height=height, scale=scale)
            if candidate is not None and (best is None or candidate.score > best.score):
                best = candidate

        if best is None or not best.presence or best.score < self._config.min_confidence:
            return None

        return LocatedRegion(
            rect=RoiRect(
                x1=best.x,
                x2=best.x + best.width,
                y1=best.y,
                y2=best.y + best.height,
            ),
            confidence=best.score,
            scale=best.scale,
        )

    def _locate_size(
        self,
        frame: np.ndarray,
        *,
        width: int,
        height: int,
        scale: float,
    ) -> _Candidate | None:
        stride = max(8, round(min(width, height) * self._config.coarse_stride_fraction))
        coarse: list[_Candidate] = []
        max_y = int(frame.shape[0]) - height
        max_x = int(frame.shape[1]) - width

        for y in range(0, max_y + 1, stride):
            for x in range(0, max_x + 1, stride):
                candidate = self._score_candidate(
                    frame,
                    x=x,
                    y=y,
                    width=width,
                    height=height,
                    scale=scale,
                )
                coarse.append(candidate)

        if not coarse:
            return None
        coarse.sort(key=lambda item: item.score, reverse=True)

        best: _Candidate | None = None
        refine_step = max(1, stride // 8)
        for seed in coarse[: self._config.coarse_candidate_count]:
            x_start = max(0, seed.x - stride)
            x_end = min(max_x, seed.x + stride)
            y_start = max(0, seed.y - stride)
            y_end = min(max_y, seed.y + stride)
            for y in range(y_start, y_end + 1, refine_step):
                for x in range(x_start, x_end + 1, refine_step):
                    candidate = self._score_candidate(
                        frame,
                        x=x,
                        y=y,
                        width=width,
                        height=height,
                        scale=scale,
                    )
                    if best is None or candidate.score > best.score:
                        best = candidate
        return best

    def _score_candidate(
        self,
        frame: np.ndarray,
        *,
        x: int,
        y: int,
        width: int,
        height: int,
        scale: float,
    ) -> _Candidate:
        crop = np.ascontiguousarray(frame[y : y + height, x : x + width])
        presence = self._presence_detector.detect(crop)
        line_score = _major_line_score(crop)
        border_score = _border_score(crop)
        score = presence.score * 0.65 + line_score * 0.25 + border_score * 0.10
        return _Candidate(
            x=x,
            y=y,
            width=width,
            height=height,
            scale=scale,
            score=float(score),
            presence=presence.present,
        )


def _major_line_score(crop: np.ndarray) -> float:
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 40, 120) > 0
    specs = (
        ((0.485, 0.02, 0.505, 0.98), (0.455, 0.02, 0.475, 0.98), (0.515, 0.02, 0.535, 0.98)),
        ((0.50, 0.325, 0.99, 0.345), (0.50, 0.285, 0.99, 0.305), (0.50, 0.365, 0.99, 0.385)),
        ((0.50, 0.695, 0.99, 0.715), (0.50, 0.655, 0.99, 0.675), (0.50, 0.735, 0.99, 0.755)),
        ((0.01, 0.685, 0.49, 0.705), (0.01, 0.645, 0.49, 0.665), (0.01, 0.725, 0.49, 0.745)),
    )
    scores: list[float] = []
    for line_rect, before_rect, after_rect in specs:
        line_density = _edge_density(_crop_relative(edges, line_rect))
        neighbor_density = (
            _edge_density(_crop_relative(edges, before_rect))
            + _edge_density(_crop_relative(edges, after_rect))
        ) / 2.0
        scores.append(min(max(line_density - neighbor_density, 0.0) / 0.10, 1.0))
    return float(sum(scores) / len(scores))


def _border_score(crop: np.ndarray) -> float:
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 40, 120) > 0
    specs = (
        ((0.00, 0.00, 1.00, 0.02), (0.00, 0.03, 1.00, 0.05)),
        ((0.00, 0.98, 1.00, 1.00), (0.00, 0.95, 1.00, 0.97)),
        ((0.00, 0.00, 0.02, 1.00), (0.03, 0.00, 0.05, 1.00)),
        ((0.98, 0.00, 1.00, 1.00), (0.95, 0.00, 0.97, 1.00)),
    )
    scores: list[float] = []
    for border_rect, inside_rect in specs:
        border_density = _edge_density(_crop_relative(edges, border_rect))
        inside_density = _edge_density(_crop_relative(edges, inside_rect))
        scores.append(min(max(border_density - inside_density, 0.0) / 0.08, 1.0))
    return float(sum(scores) / len(scores))


def _crop_relative(image: np.ndarray, rect: tuple[float, float, float, float]) -> np.ndarray:
    height = int(image.shape[0])
    width = int(image.shape[1])
    x1 = max(0, min(width, int(width * rect[0])))
    y1 = max(0, min(height, int(height * rect[1])))
    x2 = max(0, min(width, int(width * rect[2])))
    y2 = max(0, min(height, int(height * rect[3])))
    if x2 <= x1 or y2 <= y1:
        return np.zeros((1, 1), dtype=image.dtype)
    return np.ascontiguousarray(image[y1:y2, x1:x2])


def _edge_density(edge_mask: np.ndarray) -> float:
    if edge_mask.size == 0:
        return 0.0
    return float(np.count_nonzero(edge_mask)) / float(edge_mask.size)
