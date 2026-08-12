from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from zml_ocr_worker.calibration.model import LocatedRegion
from zml_ocr_worker.capture.model import RoiRect
from zml_ocr_worker.pipelines.mining_finder.presence import FinderPresenceDetector

RelativeRect = tuple[float, float, float, float]


@dataclass(frozen=True, slots=True)
class FinderLocatorConfig:
    baseline_client_width: int = 2560
    baseline_client_height: int = 1440
    baseline_finder_width: int = 354
    baseline_finder_height: int = 239
    baseline_finder_x_offset: int = 7
    scale_tolerance: tuple[float, ...] = (0.98, 1.0, 1.02)
    coarse_stride_fraction: float = 0.09
    coarse_candidate_count: int = 8
    min_confidence: float = 0.86


@dataclass(frozen=True, slots=True)
class _Candidate:
    x: int
    y: int
    width: int
    height: int
    scale: float
    fast_score: float


@dataclass(frozen=True, slots=True)
class _FrameFeatures:
    dark: np.ndarray
    edges: np.ndarray
    blue: np.ndarray
    green: np.ndarray


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

        features = _frame_features(frame)
        candidates: list[_Candidate] = []
        for tolerance in self._config.scale_tolerance:
            scale = base_scale * tolerance
            width = max(80, round(self._config.baseline_finder_width * scale))
            height = max(50, round(self._config.baseline_finder_height * scale))
            if width > frame_width or height > frame_height:
                continue
            candidates.extend(
                self._locate_size(
                    features,
                    frame_width=frame_width,
                    frame_height=frame_height,
                    width=width,
                    height=height,
                    scale=scale,
                )
            )

        candidates.sort(key=lambda item: item.fast_score, reverse=True)
        best: tuple[float, _Candidate] | None = None
        for candidate in candidates[: self._config.coarse_candidate_count * 2]:
            crop = np.ascontiguousarray(
                frame[
                    candidate.y : candidate.y + candidate.height,
                    candidate.x : candidate.x + candidate.width,
                ]
            )
            presence = self._presence_detector.detect(crop)
            if not presence.present:
                continue
            confidence = presence.score * 0.65 + candidate.fast_score * 0.35
            if best is None or confidence > best[0]:
                best = (float(confidence), candidate)

        if best is None or best[0] < self._config.min_confidence:
            return None

        confidence, candidate = best
        x_offset = round(self._config.baseline_finder_x_offset * candidate.scale)
        x1 = min(max(0, candidate.x + x_offset), frame_width - candidate.width)
        return LocatedRegion(
            rect=RoiRect(
                x1=x1,
                x2=x1 + candidate.width,
                y1=candidate.y,
                y2=candidate.y + candidate.height,
            ),
            confidence=confidence,
            scale=candidate.scale,
        )

    def _locate_size(
        self,
        features: _FrameFeatures,
        *,
        frame_width: int,
        frame_height: int,
        width: int,
        height: int,
        scale: float,
    ) -> list[_Candidate]:
        # The full-frame coarse grid used to call _fast_score from nested Python loops.
        # Even on a ThreadPoolExecutor that work still competes for the GIL with the
        # capture/position loop. Score the whole coarse grid through NumPy/integral
        # image indexing instead, then keep the small bounded refinement passes in
        # Python where their candidate count is tiny.
        stride = max(8, round(min(width, height) * self._config.coarse_stride_fraction))
        max_y = frame_height - height
        max_x = frame_width - width
        coarse = _coarse_candidates(
            features,
            max_x=max_x,
            max_y=max_y,
            stride=stride,
            width=width,
            height=height,
            scale=scale,
            count=self._config.coarse_candidate_count,
        )

        medium_step = max(2, stride // 4)
        medium: dict[tuple[int, int], _Candidate] = {}
        for seed in coarse:
            for y in _bounded_positions(seed.y, stride, medium_step, max_y):
                for x in _bounded_positions(seed.x, stride, medium_step, max_x):
                    candidate = _Candidate(
                        x=x,
                        y=y,
                        width=width,
                        height=height,
                        scale=scale,
                        fast_score=_fast_score(features, x=x, y=y, width=width, height=height),
                    )
                    key = (x, y)
                    previous = medium.get(key)
                    if previous is None or candidate.fast_score > previous.fast_score:
                        medium[key] = candidate

        medium_ranked = sorted(medium.values(), key=lambda item: item.fast_score, reverse=True)
        exact: dict[tuple[int, int], _Candidate] = {}
        exact_seed_count = max(2, self._config.coarse_candidate_count // 2)
        for seed in medium_ranked[:exact_seed_count]:
            for y in _bounded_positions(seed.y, medium_step, 1, max_y):
                for x in _bounded_positions(seed.x, medium_step, 1, max_x):
                    candidate = _Candidate(
                        x=x,
                        y=y,
                        width=width,
                        height=height,
                        scale=scale,
                        fast_score=_fast_score(features, x=x, y=y, width=width, height=height),
                    )
                    key = (x, y)
                    previous = exact.get(key)
                    if previous is None or candidate.fast_score > previous.fast_score:
                        exact[key] = candidate

        result = sorted(exact.values(), key=lambda item: item.fast_score, reverse=True)
        return result[: self._config.coarse_candidate_count]


def _frame_features(frame: np.ndarray) -> _FrameFeatures:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 40, 120) > 0
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    hue = hsv[:, :, 0]
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]
    blue = (hue >= 85) & (hue <= 130) & (saturation >= 60) & (value >= 50)
    green = (hue >= 45) & (hue <= 80) & (saturation >= 70) & (value >= 70)
    return _FrameFeatures(
        dark=cv2.integral((gray <= 70).astype(np.uint8), sdepth=cv2.CV_64F),
        edges=cv2.integral(edges.astype(np.uint8), sdepth=cv2.CV_64F),
        blue=cv2.integral(blue.astype(np.uint8), sdepth=cv2.CV_64F),
        green=cv2.integral(green.astype(np.uint8), sdepth=cv2.CV_64F),
    )


def _coarse_candidates(
    features: _FrameFeatures,
    *,
    max_x: int,
    max_y: int,
    stride: int,
    width: int,
    height: int,
    scale: float,
    count: int,
) -> list[_Candidate]:
    xs = np.asarray(_scan_positions(max_x, stride), dtype=np.int32)
    ys = np.asarray(_scan_positions(max_y, stride), dtype=np.int32)
    if xs.size == 0 or ys.size == 0 or count <= 0:
        return []

    scores = _fast_score_grid(features, xs=xs, ys=ys, width=width, height=height)
    flat = scores.reshape(-1)
    keep = min(int(count), int(flat.size))
    if keep <= 0:
        return []

    if keep == flat.size:
        indices = np.argsort(flat)[::-1]
    else:
        indices = np.argpartition(flat, -keep)[-keep:]
        indices = indices[np.argsort(flat[indices])[::-1]]

    nx = int(xs.size)
    return [
        _Candidate(
            x=int(xs[int(index) % nx]),
            y=int(ys[int(index) // nx]),
            width=width,
            height=height,
            scale=scale,
            fast_score=float(flat[int(index)]),
        )
        for index in indices
    ]


def _fast_score_grid(
    features: _FrameFeatures,
    *,
    xs: np.ndarray,
    ys: np.ndarray,
    width: int,
    height: int,
) -> np.ndarray:
    panel_rects: tuple[RelativeRect, ...] = (
        (0.05, 0.05, 0.45, 0.68),
        (0.52, 0.05, 0.96, 0.32),
        (0.52, 0.39, 0.96, 0.68),
        (0.52, 0.74, 0.96, 0.96),
    )
    panel_dark_score = sum(
        _rect_ratio_grid(features.dark, xs=xs, ys=ys, width=width, height=height, rect=rect)
        for rect in panel_rects
    ) / float(len(panel_rects))

    line_specs: tuple[tuple[RelativeRect, RelativeRect, RelativeRect], ...] = (
        (
            (0.485, 0.02, 0.505, 0.98),
            (0.455, 0.02, 0.475, 0.98),
            (0.515, 0.02, 0.535, 0.98),
        ),
        (
            (0.01, 0.685, 0.49, 0.705),
            (0.01, 0.645, 0.49, 0.665),
            (0.01, 0.725, 0.49, 0.745),
        ),
        (
            (0.50, 0.325, 0.99, 0.345),
            (0.50, 0.285, 0.99, 0.305),
            (0.50, 0.365, 0.99, 0.385),
        ),
        (
            (0.50, 0.695, 0.99, 0.715),
            (0.50, 0.655, 0.99, 0.675),
            (0.50, 0.735, 0.99, 0.755),
        ),
    )
    grid_score = np.zeros_like(panel_dark_score, dtype=np.float64)
    for line_rect, before_rect, after_rect in line_specs:
        line_density = _rect_ratio_grid(
            features.edges,
            xs=xs,
            ys=ys,
            width=width,
            height=height,
            rect=line_rect,
        )
        neighbor_density = (
            _rect_ratio_grid(
                features.edges,
                xs=xs,
                ys=ys,
                width=width,
                height=height,
                rect=before_rect,
            )
            + _rect_ratio_grid(
                features.edges,
                xs=xs,
                ys=ys,
                width=width,
                height=height,
                rect=after_rect,
            )
        ) / 2.0
        grid_score += np.clip((line_density - neighbor_density) / 0.08, 0.0, 1.0)
    grid_score /= float(len(line_specs))

    whole = (0.0, 0.0, 1.0, 1.0)
    blue_score = np.clip(
        _rect_ratio_grid(features.blue, xs=xs, ys=ys, width=width, height=height, rect=whole)
        / 0.025,
        0.0,
        1.0,
    )
    green_score = np.clip(
        _rect_ratio_grid(features.green, xs=xs, ys=ys, width=width, height=height, rect=whole)
        / 0.035,
        0.0,
        1.0,
    )
    return panel_dark_score * 0.45 + grid_score * 0.35 + blue_score * 0.15 + green_score * 0.05


def _fast_score(
    features: _FrameFeatures,
    *,
    x: int,
    y: int,
    width: int,
    height: int,
) -> float:
    panel_rects: tuple[RelativeRect, ...] = (
        (0.05, 0.05, 0.45, 0.68),
        (0.52, 0.05, 0.96, 0.32),
        (0.52, 0.39, 0.96, 0.68),
        (0.52, 0.74, 0.96, 0.96),
    )
    panel_dark_score = sum(
        _rect_ratio(features.dark, x=x, y=y, width=width, height=height, rect=rect)
        for rect in panel_rects
    ) / len(panel_rects)

    line_specs: tuple[tuple[RelativeRect, RelativeRect, RelativeRect], ...] = (
        (
            (0.485, 0.02, 0.505, 0.98),
            (0.455, 0.02, 0.475, 0.98),
            (0.515, 0.02, 0.535, 0.98),
        ),
        (
            (0.01, 0.685, 0.49, 0.705),
            (0.01, 0.645, 0.49, 0.665),
            (0.01, 0.725, 0.49, 0.745),
        ),
        (
            (0.50, 0.325, 0.99, 0.345),
            (0.50, 0.285, 0.99, 0.305),
            (0.50, 0.365, 0.99, 0.385),
        ),
        (
            (0.50, 0.695, 0.99, 0.715),
            (0.50, 0.655, 0.99, 0.675),
            (0.50, 0.735, 0.99, 0.755),
        ),
    )
    grid_scores: list[float] = []
    for line_rect, before_rect, after_rect in line_specs:
        line_density = _rect_ratio(
            features.edges,
            x=x,
            y=y,
            width=width,
            height=height,
            rect=line_rect,
        )
        neighbor_density = (
            _rect_ratio(
                features.edges,
                x=x,
                y=y,
                width=width,
                height=height,
                rect=before_rect,
            )
            + _rect_ratio(
                features.edges,
                x=x,
                y=y,
                width=width,
                height=height,
                rect=after_rect,
            )
        ) / 2.0
        grid_scores.append(min(max(line_density - neighbor_density, 0.0) / 0.08, 1.0))
    grid_score = sum(grid_scores) / len(grid_scores)

    whole = (0.0, 0.0, 1.0, 1.0)
    blue_score = min(
        _rect_ratio(features.blue, x=x, y=y, width=width, height=height, rect=whole) / 0.025,
        1.0,
    )
    green_score = min(
        _rect_ratio(features.green, x=x, y=y, width=width, height=height, rect=whole) / 0.035,
        1.0,
    )
    return float(
        panel_dark_score * 0.45 + grid_score * 0.35 + blue_score * 0.15 + green_score * 0.05
    )


def _rect_ratio_grid(
    integral: np.ndarray,
    *,
    xs: np.ndarray,
    ys: np.ndarray,
    width: int,
    height: int,
    rect: RelativeRect,
) -> np.ndarray:
    left = xs + int(width * rect[0])
    top = ys + int(height * rect[1])
    right = xs + int(width * rect[2])
    bottom = ys + int(height * rect[3])
    area = max(1, (int(width * rect[2]) - int(width * rect[0]))) * max(
        1,
        int(height * rect[3]) - int(height * rect[1]),
    )
    total = (
        integral[np.ix_(bottom, right)]
        - integral[np.ix_(top, right)]
        - integral[np.ix_(bottom, left)]
        + integral[np.ix_(top, left)]
    )
    return total / float(area)


def _rect_ratio(
    integral: np.ndarray,
    *,
    x: int,
    y: int,
    width: int,
    height: int,
    rect: RelativeRect,
) -> float:
    x1 = x + int(width * rect[0])
    y1 = y + int(height * rect[1])
    x2 = x + int(width * rect[2])
    y2 = y + int(height * rect[3])
    if x2 <= x1 or y2 <= y1:
        return 0.0
    total = integral[y2, x2] - integral[y1, x2] - integral[y2, x1] + integral[y1, x1]
    return float(total) / float((x2 - x1) * (y2 - y1))


def _scan_positions(limit: int, stride: int) -> list[int]:
    positions = list(range(0, limit + 1, stride))
    if not positions or positions[-1] != limit:
        positions.append(limit)
    return positions


def _bounded_positions(center: int, radius: int, step: int, limit: int) -> range:
    start = max(0, center - radius)
    end = min(limit, center + radius)
    return range(start, end + 1, max(1, step))
