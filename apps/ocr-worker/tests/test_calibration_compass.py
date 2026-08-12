from __future__ import annotations

import cv2
import numpy as np

from zml_ocr_worker.calibration.compass import CompassLocator, CompassLocatorConfig


def _radar_frame(*, center: tuple[int, int], radius: int) -> np.ndarray:
    frame = np.full((720, 1280, 3), 80, dtype=np.uint8)
    for fraction in (0.2, 0.4, 0.6, 0.8, 1.0):
        cv2.circle(
            frame,
            center,
            round(radius * fraction),
            (220, 220, 220),
            2,
            cv2.LINE_AA,
        )
    return frame


def test_compass_locator_finds_concentric_radar_and_scale() -> None:
    center = (900, 480)
    radius = 90
    frame = _radar_frame(center=center, radius=radius)

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


def test_locked_compass_requires_consecutive_invalid_checks() -> None:
    center = (900, 480)
    radius = 90
    frame = _radar_frame(center=center, radius=radius)

    locator = CompassLocator(
        config=CompassLocatorConfig(
            hough_param2=20.0,
            min_ring_contrast=0.55,
            locked_validation_failures_before_invalid=2,
        )
    )
    located = locator.locate(frame)
    assert located is not None

    blank = np.full_like(frame, 80)
    assert locator.locked_is_valid(blank, located)
    assert not locator.locked_is_valid(blank, located)

    # A valid check resets the miss streak, so one later noisy frame cannot drop the lock.
    assert locator.locked_is_valid(frame, located)
    assert locator.locked_is_valid(blank, located)


def test_locked_compass_ignores_dynamic_status_icons_near_lower_right_radar_edge() -> None:
    center = (900, 480)
    radius = 90
    clean = _radar_frame(center=center, radius=radius)
    config = CompassLocatorConfig(
        hough_param2=20.0,
        min_ring_contrast=0.55,
    )
    locator = CompassLocator(config=config)
    located = locator.locate(clean)
    assert located is not None

    # Entropia status icons beside the lower-right radar edge can switch between
    # green/yellow/red depending on zone state. They may overlap a localized slice
    # of the outer rings but must not make a stationary Compass look invalid.
    icon_centers = (
        (round(center[0] + radius * 0.78), round(center[1] + radius * 0.28)),
        (round(center[0] + radius * 0.88), round(center[1] + radius * 0.43)),
        (round(center[0] + radius * 0.72), round(center[1] + radius * 0.58)),
    )
    for color in ((30, 220, 30), (20, 220, 240), (30, 30, 240)):
        noisy = clean.copy()
        for x, y in icon_centers:
            cv2.rectangle(noisy, (x - 7, y - 7), (x + 7, y + 7), color, -1, cv2.LINE_AA)
            cv2.line(noisy, (x - 5, y), (x + 5, y), (245, 245, 245), 1, cv2.LINE_AA)
            cv2.line(noisy, (x, y - 5), (x, y + 5), (245, 245, 245), 1, cv2.LINE_AA)

        score = locator.validate_locked(noisy, located)
        assert score >= config.locked_validation_min_score
        assert locator.locked_is_valid(noisy, located)


def test_compass_locator_returns_none_without_concentric_rings() -> None:
    frame = np.full((720, 1280, 3), 80, dtype=np.uint8)

    assert CompassLocator().locate(frame) is None
