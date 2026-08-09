from pathlib import Path

import pytest

from zml_game_bridge import paths


def test_app_data_dir_honors_explicit_environment_override(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    configured_path = tmp_path / "custom-app-data"
    monkeypatch.setenv("ZML_APP_DATA_DIR", str(configured_path))

    assert paths.get_app_data_dir() == configured_path


def test_source_runtime_uses_workspace_local_app_data(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bridge_root = tmp_path / "apps" / "game-bridge"
    monkeypatch.delenv("ZML_APP_DATA_DIR", raising=False)
    monkeypatch.setattr(paths.sys, "frozen", False, raising=False)
    monkeypatch.setattr(paths, "get_bridge_project_root", lambda: bridge_root)

    assert paths.get_app_data_dir() == tmp_path / ".tmp" / "appdata" / "backend"


def test_frozen_runtime_keeps_live_local_app_data(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("ZML_APP_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(paths.sys, "frozen", True, raising=False)

    assert paths.get_app_data_dir() == tmp_path / "z-mining-log"
