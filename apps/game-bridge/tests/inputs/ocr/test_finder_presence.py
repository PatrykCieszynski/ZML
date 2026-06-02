from __future__ import annotations

import cv2
import numpy as np

from zml_game_bridge.inputs.ocr.pipelines.mining_finder.presence import FinderPresenceDetector


def test_finder_presence_detector_accepts_finder_like_panel() -> None:
    detector = FinderPresenceDetector()

    result = detector.detect(_finder_like_crop())

    assert result.present is True
    assert result.panel_dark_score >= 0.55
    assert result.grid_score >= 0.20


def test_finder_presence_detector_rejects_plain_dark_crop() -> None:
    detector = FinderPresenceDetector()
    crop = np.full((240, 340, 3), (30, 30, 30), dtype=np.uint8)

    result = detector.detect(crop)

    assert result.present is False


def test_finder_presence_detector_rejects_textured_world_crop() -> None:
    detector = FinderPresenceDetector()
    rng = np.random.default_rng(7)
    crop = rng.normal(loc=(70, 95, 72), scale=12, size=(240, 340, 3))
    crop = np.clip(crop, 0, 255).astype(np.uint8)

    result = detector.detect(crop)

    assert result.present is False


def test_finder_presence_detector_rejects_bright_diagonal_edges() -> None:
    detector = FinderPresenceDetector()
    crop = np.full((240, 340, 3), (180, 170, 145), dtype=np.uint8)
    cv2.line(crop, (0, 210), (260, 0), (20, 20, 20), 5)
    cv2.line(crop, (240, 0), (330, 230), (30, 80, 140), 4)

    result = detector.detect(crop)

    assert result.present is False


def _finder_like_crop() -> np.ndarray:
    crop = np.full((240, 340, 3), (22, 26, 32), dtype=np.uint8)
    border = (150, 90, 25)
    panel = (26, 31, 39)
    green = (45, 220, 55)

    for rect in (
        (8, 10, 166, 166),
        (176, 10, 338, 80),
        (176, 88, 338, 166),
        (176, 170, 338, 230),
        (8, 170, 166, 230),
    ):
        x1, y1, x2, y2 = rect
        cv2.rectangle(crop, (x1, y1), (x2, y2), panel, thickness=-1)
        cv2.rectangle(crop, (x1, y1), (x2, y2), border, thickness=2)

    center = (86, 86)
    for radius in (22, 38, 55):
        cv2.circle(crop, center, radius, border, thickness=1)
    cv2.circle(crop, (80, 202), 20, green, thickness=3)
    cv2.circle(crop, (124, 202), 20, green, thickness=3)
    cv2.putText(
        crop,
        "UNIVERSAL AMMO",
        (184, 192),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (230, 230, 230),
        1,
    )
    return crop
