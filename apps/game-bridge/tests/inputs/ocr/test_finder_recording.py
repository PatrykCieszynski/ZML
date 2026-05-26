from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from zml_game_bridge.inputs.ocr.pipelines.mining_finder.model import (
    FinderFeatures,
    MiningFinderSignal,
)
from zml_game_bridge.inputs.ocr.pipelines.mining_finder.recording import (
    FinderCropRecorder,
    FinderRecordingConfig,
    finder_recording_config_from_env,
)


def test_finder_crop_recorder_writes_state_change_sample(tmp_path: Path) -> None:
    recorder = FinderCropRecorder(
        config=FinderRecordingConfig(modes=frozenset({"state-change"}), root_dir=tmp_path),
        roi_name="finder_test",
    )
    crop = np.zeros((8, 12, 4), dtype=np.uint8)

    recorder.record_frame(
        crop,
        ts_ms=1_000,
        features=FinderFeatures(status_kind="idle", raw_status_text="Press E to initiate survey"),
        signals=[],
    )
    recorder.record_frame(
        crop,
        ts_ms=1_100,
        features=FinderFeatures(status_kind="idle", raw_status_text="Press E to initiate survey"),
        signals=[],
    )

    png_files = sorted(tmp_path.glob("*.png"))
    json_files = sorted(tmp_path.glob("*.json"))
    assert len(png_files) == 1
    assert len(json_files) == 1

    metadata = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert metadata["roi_name"] == "finder_test"
    assert metadata["reasons"] == ["state-change"]
    assert metadata["features"]["status_kind"] == "idle"
    assert metadata["image_shape"] == [8, 12, 4]


def test_finder_crop_recorder_writes_manual_sample_and_consumes_trigger(tmp_path: Path) -> None:
    recorder = FinderCropRecorder(
        config=FinderRecordingConfig(modes=frozenset({"manual"}), root_dir=tmp_path),
        roi_name="finder_test",
    )
    trigger = tmp_path / "record-now.flag"
    trigger.write_text("", encoding="utf-8")

    recorder.record_frame(
        np.zeros((2, 3, 4), dtype=np.uint8),
        ts_ms=1_000,
        features=FinderFeatures(status_kind="idle"),
        signals=[],
    )

    assert not trigger.exists()
    assert len(list(tmp_path.glob("*.png"))) == 1
    metadata = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert metadata["reasons"] == ["manual"]


def test_finder_crop_recorder_throttles_interval_and_low_confidence(tmp_path: Path) -> None:
    recorder = FinderCropRecorder(
        config=FinderRecordingConfig(
            modes=frozenset({"interval", "low-confidence"}),
            root_dir=tmp_path,
            interval_ms=1_000,
            low_confidence_min_interval_ms=1_000,
        ),
        roi_name="finder_test",
    )
    crop = np.zeros((2, 3, 4), dtype=np.uint8)

    for ts_ms in (1_000, 1_500, 2_000):
        recorder.record_frame(
            crop,
            ts_ms=ts_ms,
            features=FinderFeatures(status_kind=None),
            signals=[],
        )

    assert len(list(tmp_path.glob("*.png"))) == 2


def test_finder_recording_config_from_env_parses_modes(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("ZML_FINDER_RECORDING", "manual,state-change,interval")
    monkeypatch.setenv("ZML_FINDER_RECORDING_DIR", str(tmp_path))
    monkeypatch.setenv("ZML_FINDER_RECORDING_INTERVAL_S", "2.5")

    config = finder_recording_config_from_env()

    assert config.modes == frozenset({"manual", "state-change", "interval"})
    assert config.root_dir == tmp_path
    assert config.interval_ms == 2_500


def test_finder_crop_recorder_records_signals_in_metadata(tmp_path: Path) -> None:
    recorder = FinderCropRecorder(
        config=FinderRecordingConfig(modes=frozenset({"state-change"}), root_dir=tmp_path),
        roi_name="finder_test",
    )

    recorder.record_frame(
        np.zeros((2, 3, 4), dtype=np.uint8),
        ts_ms=1_000,
        features=FinderFeatures(status_kind="sending_probe"),
        signals=[MiningFinderSignal(ts_ms=1_000, kind="probe_fired", modes_mask=1)],
    )

    metadata = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert metadata["signals"][0]["kind"] == "probe_fired"
    assert metadata["signals"][0]["modes_mask"] == 1
