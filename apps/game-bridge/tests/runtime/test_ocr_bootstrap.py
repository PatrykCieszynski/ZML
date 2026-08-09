from __future__ import annotations

import sys
from pathlib import Path

import pytest

from zml_game_bridge.inputs.ocr.source import EmbeddedOcrInputSource
from zml_game_bridge.runtime.bootstrap import build_ocr_input_source
from zml_game_bridge.runtime.ocr_agent.supervisor import OcrAgentSupervisor
from zml_game_bridge.runtime.supervisor import WorkerSupervisor
from zml_game_bridge.settings import Settings


def test_embedded_transport_remains_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ZML_OCR_TRANSPORT", raising=False)
    settings = Settings(ocr_enabled=False)

    source = build_ocr_input_source(
        settings,
        supervisor=_supervisor(settings),
        position_sink=lambda _snapshot: None,
        signal_sink=lambda _signal: None,
    )

    assert settings.ocr_transport == "embedded"
    assert isinstance(source, EmbeddedOcrInputSource)


def test_agent_transport_uses_current_python_or_configured_executable(tmp_path: Path) -> None:
    default_settings = Settings(
        ocr_enabled=False,
        ocr_transport="agent",
        ocr_profile_path=tmp_path / "default-profile.json",
    )
    configured_settings = Settings(
        ocr_enabled=False,
        ocr_transport="agent",
        ocr_agent_path=Path("C:/ZML/zml-ocr-agent.exe"),
        ocr_profile_path=tmp_path / "configured-profile.json",
    )

    default_source = build_ocr_input_source(
        default_settings,
        supervisor=_supervisor(default_settings),
        position_sink=lambda _snapshot: None,
        signal_sink=lambda _signal: None,
    )
    configured_source = build_ocr_input_source(
        configured_settings,
        supervisor=_supervisor(configured_settings),
        position_sink=lambda _snapshot: None,
        signal_sink=lambda _signal: None,
    )

    assert isinstance(default_source, OcrAgentSupervisor)
    assert default_source.config.process.command == (sys.executable, "-m", "zml_ocr_agent", "stdio")
    assert isinstance(configured_source, OcrAgentSupervisor)
    assert configured_source.config.process.command == ("C:\\ZML\\zml-ocr-agent.exe", "stdio")
    assert configured_source.config.process.environment == {}
    assert configured_source.config.desired_config.revision == 1
    assert configured_source.config.desired_config.config.roi_profile.name == "mvp-default"


def test_invalid_ocr_transport_environment_fails_fast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ZML_OCR_TRANSPORT", "sidecar-ish")

    with pytest.raises(ValueError, match="ZML_OCR_TRANSPORT"):
        Settings()


def _supervisor(settings: Settings) -> WorkerSupervisor:
    supervisor = WorkerSupervisor()
    supervisor.register("ocr_worker", enabled=settings.ocr_enabled)
    return supervisor
