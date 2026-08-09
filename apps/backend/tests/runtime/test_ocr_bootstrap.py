from __future__ import annotations

from pathlib import Path

from zml_backend.runtime.bootstrap import build_ocr_input_source
from zml_backend.runtime.ocr_worker.supervisor import OcrWorkerSupervisor
from zml_backend.runtime.supervisor import WorkerSupervisor
from zml_backend.settings import Settings


def test_ocr_always_uses_external_process_from_path_or_configured_executable(
    tmp_path: Path,
) -> None:
    default_settings = Settings(
        ocr_enabled=False,
        ocr_profile_path=tmp_path / "default-profile.json",
    )
    configured_settings = Settings(
        ocr_enabled=False,
        ocr_worker_path=Path("C:/ZML/zml-ocr-worker.exe"),
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

    assert isinstance(default_source, OcrWorkerSupervisor)
    assert default_source.config.process.command == ("zml-ocr-worker", "stdio")
    assert isinstance(configured_source, OcrWorkerSupervisor)
    assert configured_source.config.process.command == ("C:\\ZML\\zml-ocr-worker.exe", "stdio")
    assert configured_source.config.process.environment == {}
    assert configured_source.config.desired_config.revision == 1
    assert configured_source.config.desired_config.config.roi_profile.name == "mvp-default"


def _supervisor(settings: Settings) -> WorkerSupervisor:
    supervisor = WorkerSupervisor()
    supervisor.register("ocr_worker", enabled=settings.ocr_enabled)
    return supervisor
