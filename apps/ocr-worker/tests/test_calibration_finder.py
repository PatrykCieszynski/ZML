from __future__ import annotations

import cv2
import numpy as np

from zml_ocr_worker.calibration.finder import FinderLocator


def test_finder_locator_finds_movable_panel_at_resolution_derived_size() -> None:
    frame = np.full((720, 1280, 3), (110, 120, 100), dtype=np.uint8)
    panel = _finder_panel(width=177, height=120)
    x = 500
    y = 400
    frame[y : y + panel.shape[0], x : x + panel.shape[1]] = panel

    located = FinderLocator().locate(frame)

    assert located is not None
    assert abs(located.rect.x1 - x) <= 4
    assert abs(located.rect.y1 - y) <= 4
    assert abs((located.rect.x2 - located.rect.x1) - panel.shape[1]) <= 4
    assert abs((located.rect.y2 - located.rect.y1) - panel.shape[0]) <= 4
    assert located.confidence >= 0.68


def test_finder_locator_returns_none_when_panel_is_absent() -> None:
    frame = np.full((720, 1280, 3), (110, 120, 100), dtype=np.uint8)

    assert FinderLocator().locate(frame) is None


def _finder_panel(*, width: int, height: int) -> np.ndarray:
    panel = np.full((height, width, 3), (25, 30, 38), dtype=np.uint8)
    line_color = (90, 100, 110)
    cv2.line(
        panel,
        (round(width * 0.49), 0),
        (round(width * 0.49), height - 1),
        line_color,
        1,
    )
    for fraction in (0.34, 0.71):
        row = round(height * fraction)
        cv2.line(panel, (round(width * 0.50), row), (width - 1, row), line_color, 1)
    row = round(height * 0.70)
    cv2.line(panel, (0, row), (round(width * 0.49), row), line_color, 1)

    center = (round(width * 0.24), round(height * 0.34))
    for radius in (10, 20, 30):
        cv2.circle(panel, center, radius, (220, 110, 20), 2, cv2.LINE_AA)
    cv2.circle(
        panel,
        (round(width * 0.20), round(height * 0.85)),
        10,
        (30, 220, 30),
        -1,
    )
    cv2.rectangle(panel, (0, 0), (width - 1, height - 1), line_color, 1)
    return panel
