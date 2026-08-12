from __future__ import annotations

import json
from pathlib import Path

from zml_backend.inputs.ocr_worker.config import (
    build_desired_ocr_config,
    load_ocr_roi_profile_payload,
)
from zml_backend.settings import Settings


def test_desired_config_contains_complete_settings_snapshot(tmp_path: Path) -> None:
    settings = Settings(
        ocr_profile_path=tmp_path / "ocr-profile.json",
        ocr_capture_hz=8.0,
        ocr_capture_artifacts_dir=tmp_path / "captures",
        finder_debug_logging=True,
        finder_recording_modes="manual,interval,accepted",
        finder_recording_dir=tmp_path / "finder",
        finder_recording_interval_s=2.5,
        finder_recording_max_samples=3,
        finder_presence_check_enabled=False,
        position_roi_snapshot_enabled=True,
        position_roi_snapshot_dir=tmp_path / "position",
        position_roi_snapshot_interval_s=4.5,
        position_roi_snapshot_max_samples=5,
        ocr_profiling_enabled=True,
        ocr_profiling_interval_s=6.5,
    )

    desired = build_desired_ocr_config(settings)

    assert desired.revision == 1
    assert desired.config.capture_hz == 8.0
    assert desired.config.capture_artifacts_dir == str(tmp_path / "captures")
    assert desired.config.finder.debug_logging is True
    assert desired.config.finder.presence_check_enabled is False
    assert desired.config.finder.recording.modes == ["accepted", "interval", "manual"]
    assert desired.config.finder.recording.interval_ms == 2_500
    assert desired.config.position.snapshot_recording.enabled is True
    assert desired.config.position.snapshot_recording.interval_ms == 4_500
    assert desired.config.profiling.enabled is True
    assert desired.config.profiling.interval_ms == 6_500
    assert settings.ocr_profile_path.exists()


def test_profile_loader_merges_legacy_partial_profile_with_defaults(tmp_path: Path) -> None:
    path = tmp_path / "legacy-profile.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "name": "custom-profile",
                "screen_rois": {"finder": {"x": 25}},
                "finder_panel": {"radar": [0.1, 0.2, 0.7, 0.8]},
            }
        ),
        encoding="utf-8",
    )

    profile = load_ocr_roi_profile_payload(path)

    assert profile.schema_version == 1
    assert profile.name == "custom-profile"
    assert profile.screen_rois.finder.x == 25
    assert profile.screen_rois.finder.name == "finder_mvp_bottom_left"
    assert profile.screen_rois.compass.name == "compass_mvp_absolute"
    assert profile.finder_panel.radar.model_dump() == {
        "x1": 0.1,
        "y1": 0.2,
        "x2": 0.7,
        "y2": 0.8,
    }
    assert profile.finder_panel.details.model_dump() == {
        "x1": 0.484,
        "y1": 0.03,
        "x2": 1.0,
        "y2": 0.35,
    }


def test_profile_loader_migrates_legacy_finder_panel_defaults(tmp_path: Path) -> None:
    path = tmp_path / "legacy-profile.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "finder_panel": {
                    "radar": [0.02, 0.03, 0.48, 0.70],
                    "modes": [0.02, 0.72, 0.48, 0.98],
                    "details": [0.50, 0.03, 0.98, 0.35],
                    "units": [0.50, 0.72, 0.98, 0.98],
                    "status": [0.50, 0.36, 0.98, 0.70],
                },
            }
        ),
        encoding="utf-8",
    )

    profile = load_ocr_roi_profile_payload(path)

    assert profile.finder_panel.radar.model_dump() == {
        "x1": 0.02,
        "y1": 0.03,
        "x2": 0.464,
        "y2": 0.70,
    }
    assert profile.finder_panel.modes.model_dump() == {
        "x1": 0.02,
        "y1": 0.72,
        "x2": 0.464,
        "y2": 0.98,
    }
    assert profile.finder_panel.details.model_dump() == {
        "x1": 0.484,
        "y1": 0.03,
        "x2": 1.0,
        "y2": 0.35,
    }
    assert profile.finder_panel.units.model_dump() == {
        "x1": 0.484,
        "y1": 0.72,
        "x2": 1.0,
        "y2": 0.98,
    }
    assert profile.finder_panel.status.model_dump() == {
        "x1": 0.484,
        "y1": 0.36,
        "x2": 1.0,
        "y2": 0.70,
    }


def test_invalid_profile_falls_back_to_complete_default(tmp_path: Path) -> None:
    path = tmp_path / "invalid-profile.json"
    path.write_text('{"screen_rois":{"finder":{"width":0}}}', encoding="utf-8")

    profile = load_ocr_roi_profile_payload(path)

    assert profile.name == "mvp-default"
    assert profile.screen_rois.finder.width == 347
