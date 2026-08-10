from __future__ import annotations

from pathlib import Path
from threading import Event
from typing import Any, cast

from zml_backend.runtime.bootstrap import RuntimeComponents
from zml_backend.runtime.runtime import AppRuntime
from zml_backend.runtime.shutdown_signal import RuntimeShutdownSignal
from zml_backend.runtime.supervisor import WorkerSupervisor
from zml_backend.settings import Settings


class _OcrInputSource:
    def __init__(self) -> None:
        self.stop_event: Event | None = None
        self.stop_calls = 0

    def start(self, *, stop_event: Event) -> None:
        self.stop_event = stop_event

    def stop(self) -> None:
        self.stop_calls += 1


class _PositionService:
    def set_publisher(self, _publisher: object) -> None:
        pass


class _Channel:
    def __init__(self) -> None:
        self.closed = False
        self.items: list[object] = []

    def emit(self, item: object) -> None:
        self.items.append(item)

    def is_closed(self) -> bool:
        return self.closed

    def close(self) -> None:
        self.closed = True


class _Worker:
    def run(self, *, stop_event: Event) -> None:
        del stop_event


class _CloudSyncWorker(_Worker):
    def configure(self, *, base_url: str | None, token: str | None) -> None:
        del base_url, token

    def request_sync(self) -> None:
        pass


class _Restorer:
    def __init__(self) -> None:
        self.restore_calls = 0

    def restore(self) -> None:
        self.restore_calls += 1


class _Supervisor:
    def __init__(self) -> None:
        self.started: list[str] = []
        self.joined: list[str] = []

    def start_thread(self, *, name: str, target: object, worker_kwargs: dict[str, Any]) -> None:
        del target, worker_kwargs
        self.started.append(name)

    def join_thread(self, name: str, *, timeout_s: float = 5.0) -> bool:
        del timeout_s
        self.joined.append(name)
        return True

    def health(self) -> dict[str, object]:
        return {}


class _ShutdownSignal:
    def __init__(self) -> None:
        self.install_calls = 0

    def install_signal_forwarders(self) -> None:
        self.install_calls += 1


def test_app_runtime_delegates_ocr_lifecycle_to_input_source() -> None:
    ocr_source = _OcrInputSource()
    pending_inputs = _Channel()
    pending_events = _Channel()
    pending_db_commands = _Channel()
    restorer = _Restorer()
    components = cast(
        RuntimeComponents,
        _Components(
            ocr_source=ocr_source,
            pending_inputs=pending_inputs,
            pending_events=pending_events,
            pending_db_commands=pending_db_commands,
            restorer=restorer,
        ),
    )
    supervisor = _Supervisor()
    shutdown_signal = _ShutdownSignal()
    runtime = AppRuntime(
        settings=Settings(
            chat_log_path=Path("chat.log"),
            ocr_enabled=True,
            mock_inputs_enabled=False,
            claim_expiration_maintenance_enabled=False,
        ),
        components=components,
        supervisor=cast(WorkerSupervisor, supervisor),
        shutdown_signal=cast(RuntimeShutdownSignal, shutdown_signal),
    )

    runtime.start()

    assert ocr_source.stop_event is not None
    assert not ocr_source.stop_event.is_set()
    assert "ocr_worker" not in supervisor.started
    assert "cloud_sync" in supervisor.started
    assert restorer.restore_calls == 1
    assert shutdown_signal.install_calls == 1

    runtime.stop()

    assert ocr_source.stop_event.is_set()
    assert ocr_source.stop_calls == 1
    assert "ocr_worker" not in supervisor.joined
    assert "cloud_sync" in supervisor.joined
    assert pending_inputs.closed
    assert pending_events.closed
    assert pending_db_commands.closed


class _Components:
    def __init__(
        self,
        *,
        ocr_source: _OcrInputSource,
        pending_inputs: _Channel,
        pending_events: _Channel,
        pending_db_commands: _Channel,
        restorer: _Restorer,
    ) -> None:
        self.pending_inputs = pending_inputs
        self.pending_events = pending_events
        self.pending_db_commands = pending_db_commands
        self.persisted_events = object()
        self.position_service = _PositionService()
        self.ocr_input_source = ocr_source
        self.cloud_sync_worker = _CloudSyncWorker()
        self.mining_equipment_service = object()
        self.run_session_service = object()
        self.mining_coordinator = object()
        self.input_coordinator = _Worker()
        self.db_writer_worker = _Worker()
        self.lifecycle_restorer = restorer
