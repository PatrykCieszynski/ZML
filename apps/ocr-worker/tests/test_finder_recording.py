from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from zml_ocr_worker.pipelines.mining_finder.model import (
    FinderFeatures,
    MiningFinderSignal,
)
from zml_ocr_worker.pipelines.mining_finder.recording import (
    FinderCropRecorder,
    FinderRecordingConfig,
    finder_recording_config_from_env,
)


def test_finder_crop_recorder_writes_interval_sample(tmp_path: Path) -> None:
    recorder = FinderCropRecorder(
        config=FinderRecordingConfig(
            modes=frozenset({"interval"}),
            root_dir=tmp_path,
            interval_ms=1_000,
        ),
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
        ts_ms=1_500,
        features=FinderFeatures(status_kind="idle", raw_status_text="Press E to initiate survey"),
        signals=[],
    )

    png_files = sorted(tmp_path.glob("*.png"))
    json_files = sorted(tmp_path.glob("*.json"))
    assert len(png_files) == 1
    assert len(json_files) == 1

    metadata = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert metadata["roi_name"] == "finder_test"
    assert metadata["reasons"] == ["interval"]
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


def test_finder_crop_recorder_records_every_accepted_crop(tmp_path: Path) -> None:
    recorder = FinderCropRecorder(
        config=FinderRecordingConfig(
            modes=frozenset({"accepted"}),
            root_dir=tmp_path,
            max_samples=10,
        ),
        roi_name="finder_auto",
    )
    crop = np.zeros((8, 12, 4), dtype=np.uint8)

    recorder.record_frame(
        crop,
        ts_ms=1_000,
        features=FinderFeatures(status_kind="idle"),
        signals=[],
    )
    recorder.record_frame(
        crop,
        ts_ms=1_500,
        features=FinderFeatures(status_kind="idle"),
        signals=[],
    )

    metadata_files = sorted(tmp_path.glob("*.json"))
    assert len(list(tmp_path.glob("*.png"))) == 2
    assert len(metadata_files) == 2
    for path in metadata_files:
        metadata = json.loads(path.read_text(encoding="utf-8"))
        assert metadata["reasons"] == ["accepted"]


def test_finder_crop_recorder_respects_max_samples(tmp_path: Path) -> None:
    recorder = FinderCropRecorder(
        config=FinderRecordingConfig(
            modes=frozenset({"interval"}),
            root_dir=tmp_path,
            interval_ms=1_000,
            max_samples=2,
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
    monkeypatch.setenv("ZML_FINDER_RECORDING", "manual,interval")
    monkeypatch.setenv("ZML_FINDER_RECORDING_DIR", str(tmp_path))
    monkeypatch.setenv("ZML_FINDER_RECORDING_INTERVAL_S", "2.5")
    monkeypatch.setenv("ZML_FINDER_RECORDING_MAX_SAMPLES", "4")

    config = finder_recording_config_from_env()

    assert config.modes == frozenset({"manual", "interval"})
    assert config.root_dir == tmp_path
    assert config.interval_ms == 2_500
    assert config.max_samples == 4


def test_finder_recording_config_uses_large_default_for_accepted_mode(monkeypatch) -> None:
    monkeypatch.setenv("ZML_FINDER_RECORDING", "accepted")
    monkeypatch.delenv("ZML_FINDER_RECORDING_MAX_SAMPLES", raising=False)

    config = finder_recording_config_from_env()

    assert config.modes == frozenset({"accepted"})
    assert config.max_samples == 500


def test_finder_crop_recorder_records_signals_in_metadata(tmp_path: Path) -> None:
    recorder = FinderCropRecorder(
        config=FinderRecordingConfig(modes=frozenset({"manual"}), root_dir=tmp_path),
        roi_name="finder_test",
    )
    (tmp_path / "record-now.flag").write_text("", encoding="utf-8")

    recorder.record_frame(
        np.zeros((2, 3, 4), dtype=np.uint8),
        ts_ms=1_000,
        features=FinderFeatures(status_kind="sending_probe"),
        signals=[MiningFinderSignal(ts_ms=1_000, kind="probe_fired", modes_mask=1)],
    )

    metadata = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert metadata["signals"][0]["kind"] == "probe_fired"
    assert metadata["signals"][0]["modes_mask"] == 1
