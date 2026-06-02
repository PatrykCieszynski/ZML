from __future__ import annotations

import cv2
import numpy as np

from zml_game_bridge.domain.mining import MiningMode
from zml_game_bridge.inputs.ocr.pipelines.mining_finder.vision import (
    FinderPanelLayout,
    VisionFinderFeatureDetector,
)


def test_finder_mode_classifier_uses_only_active_icons_for_modes_mask() -> None:
    detector = VisionFinderFeatureDetector(enable_text_ocr=False)
    finder = _blank_finder_roi()
    modes = _relative_crop(finder, FinderPanelLayout().modes)
    parts = np.array_split(modes, 3, axis=1)
    parts[0][:] = (35, 230, 60)
    parts[1][:] = (35, 95, 40)
    parts[2][:] = (90, 90, 90)

    features = detector.detect(finder)

    assert features.modes_mask == int(MiningMode.ORE)
    assert features.debug["mode_ore_state"] == 2.0
    assert features.debug["mode_enmatter_state"] == 1.0
    assert features.debug["mode_treasure_state"] == 0.0


def test_finder_mode_classifier_accepts_active_treasure_without_low_inactive_noise() -> None:
    detector = VisionFinderFeatureDetector(enable_text_ocr=False)
    finder = _blank_finder_roi()
    modes = _relative_crop(finder, FinderPanelLayout().modes)
    parts = np.array_split(modes, 3, axis=1)
    parts[0][:] = (90, 90, 90)
    parts[1][:] = (90, 90, 90)
    parts[2][:] = (35, 230, 60)

    features = detector.detect(finder)

    assert features.modes_mask == int(MiningMode.TREASURE)
    assert features.debug["mode_treasure_state"] == 2.0


def test_finder_mode_classifier_supports_inactive_ore_with_active_enmatter_and_treasure() -> None:
    detector = VisionFinderFeatureDetector(enable_text_ocr=False)
    finder = _blank_finder_roi()
    modes = _relative_crop(finder, FinderPanelLayout().modes)
    parts = np.array_split(modes, 3, axis=1)
    parts[0][:] = (35, 95, 40)
    parts[1][:] = (35, 230, 60)
    parts[2][:] = (35, 230, 60)

    features = detector.detect(finder)

    assert features.modes_mask == int(MiningMode.ENMATTER | MiningMode.TREASURE)
    assert features.debug["mode_ore_state"] == 1.0
    assert features.debug["mode_enmatter_state"] == 2.0
    assert features.debug["mode_treasure_state"] == 2.0


def test_finder_mode_classifier_treats_small_green_treasure_icon_as_inactive() -> None:
    detector = VisionFinderFeatureDetector(enable_text_ocr=False)
    finder = _blank_finder_roi()
    modes = _relative_crop(finder, FinderPanelLayout().modes)
    parts = np.array_split(modes, 3, axis=1)
    parts[0][:] = (35, 230, 60)
    parts[1][:] = (35, 230, 60)
    cv2.circle(parts[2], (parts[2].shape[1] // 2, parts[2].shape[0] // 2), 15, (35, 230, 60), -1)

    features = detector.detect(finder)

    assert features.modes_mask == int(MiningMode.ORE | MiningMode.ENMATTER)
    assert features.debug["mode_treasure_state"] == 1.0


def _blank_finder_roi() -> np.ndarray:
    return np.full((240, 340, 3), (22, 26, 32), dtype=np.uint8)


def _relative_crop(img: np.ndarray, rect: tuple[float, float, float, float]) -> np.ndarray:
    height = img.shape[0]
    width = img.shape[1]
    x1 = int(width * rect[0])
    y1 = int(height * rect[1])
    x2 = int(width * rect[2])
    y2 = int(height * rect[3])
    return img[y1:y2, x1:x2]
