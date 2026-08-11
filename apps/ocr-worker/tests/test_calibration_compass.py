from __future__ import annotations

import cv2
import numpy as np

from zml_ocr_worker.calibration.compass import CompassLocator, CompassLocatorConfig


def test_compass_locator_finds_concentric_radar_and_scale() -> None:
    frame = np.full((720, 1280, 3), 80, dtype=np.uint8)
    center = (900, 480)
    radius = 90
    for fraction in (0.2, 0.4, 0.6, 0.8, 1.0):
        cv2.circle(
            frame,
            center,
            round(radius * fraction),
            (220, 220, 220),
            2,
            cv2.LINE_AA,
        )

    locator = CompassLocator(
        config=CompassLocatorConfig(
            hough_param2=20.0,
            min_ring_contrast=0.55,
        )
    )
    located = locator.locate(frame)

    assert located is not None
    assert abs(located.center_x - center[0]) <= 4
    assert abs(located.center_y - center[1]) <= 4
    assert abs(located.radius - radius) <= 5
    assert located.confidence >= 0.55


def test_compass_locator_returns_none_without_concentric_rings() -> None:
    frame = np.full((720, 1280, 3), 80, dtype=np.uint8)

    assert CompassLocator().locate(frame) is None
