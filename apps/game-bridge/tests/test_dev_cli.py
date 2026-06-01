from __future__ import annotations

import os
from pathlib import Path

from typer.testing import CliRunner

from zml_game_bridge.dev_cli import InputMode, _apply_env_overrides, app


def test_apply_env_overrides_sets_mock_mode(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "zml.sqlite3"
    chat_log_path = tmp_path / "chat.log"

    monkeypatch.delenv("ZML_OCR_ENABLED", raising=False)
    monkeypatch.delenv("ZML_MOCK_INPUTS", raising=False)
    monkeypatch.delenv("ZML_DB_PATH", raising=False)
    monkeypatch.delenv("ZML_CHAT_LOG_PATH", raising=False)
    monkeypatch.delenv("ZML_OCR_PROFILE_PATH", raising=False)
    monkeypatch.delenv("ZML_FINDER_DEBUG", raising=False)
    monkeypatch.delenv("ZML_FINDER_RECORDING", raising=False)
    monkeypatch.delenv("ZML_FINDER_RECORDING_DIR", raising=False)
    monkeypatch.delenv("ZML_FINDER_RECORDING_INTERVAL_S", raising=False)
    monkeypatch.delenv("ZML_POSITION_ROI_SNAPSHOTS", raising=False)
    monkeypatch.delenv("ZML_POSITION_ROI_SNAPSHOT_DIR", raising=False)
    monkeypatch.delenv("ZML_POSITION_ROI_SNAPSHOT_INTERVAL_S", raising=False)
    monkeypatch.delenv("ZML_OCR_PROFILING", raising=False)
    monkeypatch.delenv("ZML_OCR_PROFILING_INTERVAL_S", raising=False)
    monkeypatch.delenv("ZML_LOG_LEVEL", raising=False)
    monkeypatch.delenv("ZML_MOCK_MINING_INTERVAL_MS", raising=False)

    _apply_env_overrides(
        mode=InputMode.MOCK,
        db_path=db_path,
        chat_log_path=chat_log_path,
        ocr_profile_path=tmp_path / "ocr_profile.json",
        finder_debug=True,
        finder_recording="state-change",
        finder_recording_dir=tmp_path / "finder-crops",
        finder_recording_interval_s=2.5,
        position_roi_snapshots=False,
        position_roi_snapshot_dir=tmp_path / "position-roi",
        position_roi_snapshot_interval_s=5.0,
        ocr_profiling=True,
        ocr_profiling_interval_s=1.5,
        log_level="debug",
        mock_interval_ms=1_250,
    )

    assert os.environ["ZML_OCR_ENABLED"] == "0"
    assert os.environ["ZML_MOCK_INPUTS"] == "1"
    assert os.environ["ZML_DB_PATH"] == str(db_path)
    assert os.environ["ZML_CHAT_LOG_PATH"] == str(chat_log_path)
    assert os.environ["ZML_OCR_PROFILE_PATH"] == str(tmp_path / "ocr_profile.json")
    assert os.environ["ZML_FINDER_DEBUG"] == "1"
    assert os.environ["ZML_FINDER_RECORDING"] == "state-change"
    assert os.environ["ZML_FINDER_RECORDING_DIR"] == str(tmp_path / "finder-crops")
    assert os.environ["ZML_FINDER_RECORDING_INTERVAL_S"] == "2.5"
    assert os.environ["ZML_POSITION_ROI_SNAPSHOTS"] == "0"
    assert os.environ["ZML_POSITION_ROI_SNAPSHOT_DIR"] == str(tmp_path / "position-roi")
    assert os.environ["ZML_POSITION_ROI_SNAPSHOT_INTERVAL_S"] == "5.0"
    assert os.environ["ZML_OCR_PROFILING"] == "1"
    assert os.environ["ZML_OCR_PROFILING_INTERVAL_S"] == "1.5"
    assert os.environ["ZML_LOG_LEVEL"] == "DEBUG"
    assert os.environ["ZML_MOCK_MINING_INTERVAL_MS"] == "1250"


def test_config_command_prints_resolved_settings(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "zml.sqlite3"
    chat_log_path = tmp_path / "chat.log"
    chat_log_path.write_text("", encoding="utf-8")

    monkeypatch.setenv("ZML_DB_PATH", str(db_path))
    monkeypatch.setenv("ZML_CHAT_LOG_PATH", str(chat_log_path))

    result = CliRunner().invoke(app, ["config", "--mode", "mock"])

    assert result.exit_code == 0
    assert "Z Mining Log Game Bridge config" in result.output
    assert "mock_inputs_enabled" in result.output
    assert "ocr_enabled" in result.output
    assert "ocr_profile_path" in result.output
    assert "finder_recording_modes" in result.output
    assert "position_roi_snapshot_enabled" in result.output
    assert "ocr_profiling_enabled" in result.output
