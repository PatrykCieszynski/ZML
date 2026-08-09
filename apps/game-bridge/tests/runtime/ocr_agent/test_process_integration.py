from __future__ import annotations

import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest

from zml_game_bridge.application.mining.signals.finder import FinderNoResourcesSignal
from zml_game_bridge.application.position.model import PositionSnapshot
from zml_game_bridge.events.base import SignalBase
from zml_game_bridge.runtime.ocr_agent.config import build_desired_ocr_config
from zml_game_bridge.runtime.ocr_agent.process_transport import (
    OcrAgentProcessConfig,
    StdioOcrProcessTransport,
)
from zml_game_bridge.runtime.ocr_agent.supervisor import (
    OcrAgentSupervisor,
    OcrAgentSupervisorConfig,
    RestartPolicy,
)
from zml_game_bridge.runtime.supervisor import WorkerSupervisor
from zml_game_bridge.settings import Settings

_FAKE_AGENT = Path(__file__).parents[2] / "fixtures" / "fake_ocr_agent.py"


@pytest.mark.timeout(8)
@pytest.mark.parametrize("scenario", ["happy", "stderr_flood"])
def test_real_process_transport_configures_and_maps_observations(
    tmp_path: Path,
    scenario: str,
) -> None:
    harness = _start_harness(tmp_path, scenario=scenario)
    try:
        assert _wait_until(lambda: bool(harness.signals))
        assert harness.positions
        assert harness.positions[-1].position.x == 58_000
        assert isinstance(harness.signals[-1], FinderNoResourcesSignal)
        worker = harness.worker_health()
        assert worker["details"]["applied_config_revision"] == 1
        assert worker["details"]["process_state"] == "running"
    finally:
        harness.stop()


@pytest.mark.timeout(8)
def test_unavailable_window_degrades_capture_health_without_restart(tmp_path: Path) -> None:
    harness = _start_harness(tmp_path, scenario="window_unavailable")
    try:
        assert _wait_until(
            lambda: harness.worker_health()["details"].get("failure_kind") == "capture"
        )
        worker = harness.worker_health()
        assert worker["state"] == "degraded"
        assert worker["details"]["process_state"] == "window_unavailable"
        assert worker["details"]["restart_count"] == 0
    finally:
        harness.stop()


@pytest.mark.timeout(8)
@pytest.mark.parametrize("scenario", ["malformed", "no_heartbeat"])
def test_protocol_failure_or_heartbeat_timeout_restarts_without_stopping_bridge(
    tmp_path: Path,
    scenario: str,
) -> None:
    harness = _start_harness(tmp_path, scenario=scenario, heartbeat_timeout_s=0.2)
    try:
        assert _wait_until(
            lambda: cast(int, harness.worker_health()["details"].get("restart_count", 0)) >= 1
        )
        assert harness.worker_health()["details"]["failure_kind"] == "process"
    finally:
        harness.stop()


@pytest.mark.timeout(8)
def test_crash_restart_resends_full_config_before_accepting_observations(tmp_path: Path) -> None:
    harness = _start_harness(
        tmp_path,
        scenario="crash_once",
        extra_environment={"ZML_FAKE_OCR_MARKER": str(tmp_path / "crashed.marker")},
    )
    try:
        assert _wait_until(lambda: bool(harness.signals))
        worker = harness.worker_health()
        assert worker["details"]["restart_count"] == 1
        assert worker["details"]["applied_config_revision"] == 1
        assert harness.positions
    finally:
        harness.stop()


@pytest.mark.timeout(10)
def test_stubborn_child_is_terminated_during_backend_shutdown(tmp_path: Path) -> None:
    transports: list[StdioOcrProcessTransport] = []

    def transport_factory(config: OcrAgentProcessConfig) -> StdioOcrProcessTransport:
        transport = StdioOcrProcessTransport(config)
        transports.append(transport)
        return transport

    harness = _start_harness(
        tmp_path,
        scenario="ignore_shutdown",
        transport_factory=transport_factory,
    )
    assert _wait_until(lambda: bool(harness.signals))

    harness.stop()

    assert transports
    assert transports[-1].poll() is not None


class _Harness:
    def __init__(
        self,
        *,
        source: OcrAgentSupervisor,
        supervisor: WorkerSupervisor,
        stop_event: threading.Event,
        positions: list[PositionSnapshot],
        signals: list[SignalBase],
    ) -> None:
        self.source = source
        self.supervisor = supervisor
        self.stop_event = stop_event
        self.positions = positions
        self.signals = signals

    def stop(self) -> None:
        self.stop_event.set()
        self.source.stop()

    def worker_health(self) -> dict[str, Any]:
        workers = cast(dict[str, dict[str, Any]], self.supervisor.health()["workers"])
        return workers["ocr_worker"]


def _start_harness(
    tmp_path: Path,
    *,
    scenario: str,
    heartbeat_timeout_s: float = 0.5,
    extra_environment: dict[str, str] | None = None,
    transport_factory: Callable[[OcrAgentProcessConfig], StdioOcrProcessTransport] | None = None,
) -> _Harness:
    settings = Settings(ocr_profile_path=tmp_path / "ocr-profile.json")
    environment = {"ZML_FAKE_OCR_SCENARIO": scenario}
    environment.update(extra_environment or {})
    process = OcrAgentProcessConfig(
        command=(sys.executable, str(_FAKE_AGENT)),
        environment=environment,
    )
    transports = transport_factory or StdioOcrProcessTransport
    supervisor = WorkerSupervisor()
    supervisor.register("ocr_worker", enabled=True)
    positions: list[PositionSnapshot] = []
    signals: list[SignalBase] = []
    source = OcrAgentSupervisor(
        config=OcrAgentSupervisorConfig(
            enabled=True,
            process=process,
            desired_config=build_desired_ocr_config(settings),
            handshake_timeout_s=1.0,
            config_timeout_s=1.0,
            heartbeat_timeout_s=heartbeat_timeout_s,
            monitor_interval_s=0.01,
            restart=RestartPolicy(delays_s=(0.01,), window_s=1.0, stable_reset_s=1.0),
        ),
        supervisor=supervisor,
        position_sink=positions.append,
        signal_sink=signals.append,
        transport_factory=lambda: transports(process),
    )
    stop_event = threading.Event()
    source.start(stop_event=stop_event)
    return _Harness(
        source=source,
        supervisor=supervisor,
        stop_event=stop_event,
        positions=positions,
        signals=signals,
    )


def _wait_until(predicate: Callable[[], bool], *, timeout_s: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()
