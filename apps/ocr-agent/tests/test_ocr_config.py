from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from zml_ocr_agent.config import (
    ScreenRoiConfig,
    default_ocr_roi_profile,
    load_ocr_roi_profile,
)


def test_screen_roi_supports_bottom_left_anchor() -> None:
    frame = np.zeros((100, 200, 4), dtype=np.uint8)
    roi = ScreenRoiConfig(
        name="finder",
        anchor="bottom_left",
        x=3,
        y=4,
        width=20,
        height=10,
    )

    rect = roi.to_rect(frame)
    crop = roi.crop(frame)

    assert rect.x1 == 3
    assert rect.x2 == 23
    assert rect.y1 == 86
    assert rect.y2 == 96
    assert crop is not None
    assert crop.shape == (10, 20, 4)


def test_load_ocr_roi_profile_writes_default_when_missing(tmp_path: Path) -> None:
    path = tmp_path / "ocr_profile.json"

    profile = load_ocr_roi_profile(path)

    assert profile == default_ocr_roi_profile()
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["screen_rois"]["finder"]["name"] == "finder_mvp_bottom_left"


def test_load_ocr_roi_profile_uses_json_overrides(tmp_path: Path) -> None:
    path = tmp_path / "ocr_profile.json"
    path.write_text(
        json.dumps(
            {
                "name": "custom",
                "screen_rois": {
                    "finder": {
                        "name": "finder_custom",
                        "anchor": "top_left",
                        "x": 10,
                        "y": 20,
                        "width": 300,
                        "height": 200,
                        "enabled": True,
                    },
                },
                "position_rois": {
                    "lon": {
                        "x1": 1,
                        "x2": 2,
                        "y1": 3,
                        "y2": 4,
                    },
                },
                "finder_panel": {
                    "status": [0.1, 0.2, 0.3, 0.4],
                },
            }
        ),
        encoding="utf-8",
    )

    profile = load_ocr_roi_profile(path)

    assert profile.name == "custom"
    assert profile.screen_rois.finder.name == "finder_custom"
    assert profile.screen_rois.finder.anchor == "top_left"
    assert profile.screen_rois.finder.x == 10
    assert profile.position_rois.lon.x1 == 1
    assert profile.finder_panel.status == (0.1, 0.2, 0.3, 0.4)
