from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from zml_ocr_worker.pipelines.image import to_gray_u8


@dataclass(frozen=True, slots=True)
class NumericTokenExtractorConfig:
    tophat_kernel_height_ratio: float = 0.5
    min_component_height_ratio: float = 0.25
    max_component_height_ratio: float = 0.9
    max_component_width_height_ratio: float = 1.5
    separator_gap_height_ratio: float = 0.18
    min_token_width_height_ratio: float = 1.0
    min_label_width_height_ratio: float = 0.75
    horizontal_padding_height_ratio: float = 0.06


@dataclass(frozen=True, slots=True)
class _TextCluster:
    x1: int
    x2: int
    run_count: int

    @property
    def width(self) -> int:
        return self.x2 - self.x1


class NumericTokenExtractor:
    """Extract the right-aligned numeric value from a fixed Lon/Lat line crop.

    The Entropia coordinate strings are rendered as one right-aligned line, for
    example ``Lon: 10000`` or ``Lon: 9999``. The label therefore moves together
    with the value when its digit count changes. This extractor finds the visual
    gap between the label and the right-side value using cheap image operations,
    then returns only the value crop for the existing digits-only Tesseract path.
    """

    def __init__(self, *, config: NumericTokenExtractorConfig | None = None) -> None:
        self._config = config or NumericTokenExtractorConfig()

    def extract(self, line_roi: np.ndarray) -> np.ndarray | None:
        if line_roi.size == 0:
            return None

        gray = to_gray_u8(line_roi)
        height, width = gray.shape
        if height < 4 or width < 8:
            return None

        mask = self._text_mask(gray)
        runs = _occupied_runs(np.any(mask > 0, axis=0))
        if len(runs) < 4:
            return None

        clusters = self._clusters(runs, line_height=height)
        token = self._rightmost_token(clusters, line_height=height)
        if token is None:
            return None

        padding = max(1, round(height * self._config.horizontal_padding_height_ratio))
        x1 = max(0, token.x1 - padding)
        x2 = min(width, token.x2 + padding)
        if x2 <= x1:
            return None
        return line_roi[:, x1:x2]

    def _text_mask(self, gray: np.ndarray) -> np.ndarray:
        height = gray.shape[0]
        kernel_size = max(3, round(height * self._config.tophat_kernel_height_ratio))
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))
        top = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, kernel)
        _, binary = cv2.threshold(top, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        min_height = max(2, round(height * self._config.min_component_height_ratio))
        max_height = max(min_height, round(height * self._config.max_component_height_ratio))
        max_width = max(2, round(height * self._config.max_component_width_height_ratio))

        component_count, labels, stats, _ = cv2.connectedComponentsWithStats(
            (binary > 0).astype(np.uint8),
            connectivity=8,
        )
        clean = np.zeros_like(binary)
        for label in range(1, component_count):
            component_width = int(stats[label, cv2.CC_STAT_WIDTH])
            component_height = int(stats[label, cv2.CC_STAT_HEIGHT])
            if not (min_height <= component_height <= max_height):
                continue
            if component_width > max_width:
                continue
            clean[labels == label] = 255
        return clean

    def _clusters(
        self,
        runs: tuple[tuple[int, int], ...],
        *,
        line_height: int,
    ) -> tuple[_TextCluster, ...]:
        separator_gap = max(2, round(line_height * self._config.separator_gap_height_ratio))
        groups: list[list[tuple[int, int]]] = [[runs[0]]]
        for run in runs[1:]:
            previous = groups[-1][-1]
            gap = run[0] - previous[1]
            if gap > separator_gap:
                groups.append([run])
            else:
                groups[-1].append(run)

        return tuple(
            _TextCluster(
                x1=group[0][0],
                x2=group[-1][1],
                run_count=len(group),
            )
            for group in groups
        )

    def _rightmost_token(
        self,
        clusters: tuple[_TextCluster, ...],
        *,
        line_height: int,
    ) -> _TextCluster | None:
        min_token_width = max(3, round(line_height * self._config.min_token_width_height_ratio))
        min_label_width = max(3, round(line_height * self._config.min_label_width_height_ratio))

        for index in range(len(clusters) - 1, 0, -1):
            candidate = clusters[index]
            if candidate.width < min_token_width or candidate.run_count < 2:
                continue
            if not any(
                cluster.width >= min_label_width and cluster.run_count >= 2
                for cluster in clusters[:index]
            ):
                continue
            return candidate
        return None


def _occupied_runs(occupied: np.ndarray) -> tuple[tuple[int, int], ...]:
    runs: list[tuple[int, int]] = []
    index = 0
    width = int(occupied.shape[0])
    while index < width:
        if not bool(occupied[index]):
            index += 1
            continue
        end = index + 1
        while end < width and bool(occupied[end]):
            end += 1
        runs.append((index, end))
        index = end
    return tuple(runs)
