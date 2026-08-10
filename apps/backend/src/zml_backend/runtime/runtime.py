from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from zml_backend.api.channels.position_hub import PositionHub
from zml_backend.api.channels.sse_hub import SseHub
from zml_backend.application.mining.claims.commands import (
    ExpireMiningClaimsCommand,
    ResolvePendingDropResultsCommand,
)
from zml_backend.application.mining.equipment.service import MiningEquipmentService
from zml_backend.application.mining.segments.session import RunSessionService
from zml_backend.application.position.tracking import PositionTrackingService
from zml_backend.events.envelope import EventEnvelope
from zml_backend.inputs.chat.runner import start_chat_input
from zml_backend.inputs.mock.mining import start_mock_mining_input
from zml_backend.runtime.bootstrap import RuntimeComponents
from zml_backend.runtime.channels import ChannelClosedError
from zml_backend.runtime.db_commands import DbCommand
from zml_backend.runtime.runtime_commands import RuntimeCommand, RuntimeCommandRequest
from zml_backend.runtime.shutdown_signal import (
    RuntimeShutdownSignal,
    process_shutdown_signal,
)
from zml_backend.runtime.supervisor import WorkerSupervisor
from zml_backend.settings import Settings

logger = logging.getLogger(__name__)

_CLOUD_SYNC_WAKE_EVENT_TYPES = {
    "MiningClaimCreatedEvent",
    "MiningClaimUpdatedEvent",
}


class AppRuntime:
    def __init__(
        self,
        *,
        settings: Settings,
        components: RuntimeComponents,
        supervisor: WorkerSupervisor,
        sse_hub: SseHub | None = None,
        position_hub: PositionHub | None = None,
        shutdown_signal: RuntimeShutdownSignal = process_shutdown_signal,
    ) -> None:
        self._settings = settings
        self._components = components
        self._supervisor = supervisor
        self._stop_event = threading.Event()
        self._sub_sse = None
        self._sub_cloud_sync = None
        self._sse_hub = sse_hub
        self._position_hub = position_hub
        self._shutdown_signal = shutdown_signal
        self._started = False
        self._components.position_service.set_publisher(
            None if position_hub is None else position_hub.publish_threadsafe
        )

    @property
    def db_path(self) -> Path:
        return self._settings.db_path

    @property
    def position_hub(self) -> PositionHub:
        if self._position_hub is None:
            raise RuntimeError("Position hub not attached")
        return self._position_hub

    @property
    def sse_hub(self) -> SseHub | None:
        return self._sse_hub

    @property
    def shutdown_signal(self) -> RuntimeShutdownSignal:
        return self._shutdown_signal

    @property
    def position_service(self) -> PositionTrackingService:
        return self._components.position_service

    @property
    def mining_equipment_service(self) -> MiningEquipmentService:
        return self._components.mining_equipment_service

    @property
    def run_session_service(self) -> RunSessionService:
        return self._components.run_session_service

    def execute_db_command[T](self, command: DbCommand[T], *, timeout_s: float = 5.0) -> T:
        return self._components.pending_db_commands.execute(command, timeout_s=timeout_s)

    def configure_cloud_sync(self, *, base_url: str | None, token: str | None) -> None:
        self._components.cloud_sync_worker.configure(base_url=base_url, token=token)

    def health(self) -> dict[str, object]:
        return self._supervisor.health()

    def execute_runtime_command[T](
        self,
        command: RuntimeCommand[T],
        *,
        timeout_s: float = 5.0,
    ) -> T:
        if self._stop_event.is_set():
            raise RuntimeError("Runtime is stopping")
        request = RuntimeCommandRequest(command)
        self._components.pending_inputs.emit(request)
        return request.result(timeout_s=timeout_s)

    def attach_sse_hub(self, hub: SseHub) -> None:
        self._sse_hub = hub

    def attach_position_hub(self, hub: PositionHub) -> None:
        self._position_hub = hub
        self._components.position_service.set_publisher(hub.publish_threadsafe)

    def start(self) -> None:
        if self._started:
            return
        self._shutdown_signal.install_signal_forwarders()
        if self._components.pending_inputs.is_closed():
            raise RuntimeError("Runtime cannot be restarted after shutdown")
        if self._settings.chat_log_path is None:
            raise RuntimeError("Chat log path is not set; cannot start chat input")
        self._stop_event.clear()
        self._components.lifecycle_restorer.restore()
        self._started = True
        logger.info(
            "app_started db_path=%s chat_log_path=%s mining_resource_catalog_path=%s "
            "mining_tools_path=%s ocr_profile_path=%s ocr_enabled=%s mock_inputs_enabled=%s "
            "claim_expiration_maintenance_enabled=%s cloud_sync_enabled=%s cloud_sync_base_url=%s "
            "finder_recording_modes=%s position_roi_snapshot_enabled=%s ocr_profiling_enabled=%s",
            self._settings.db_path,
            self._settings.chat_log_path,
            self._settings.mining_resource_catalog_path,
            self._settings.mining_tools_path,
            self._settings.ocr_profile_path,
            self._settings.ocr_enabled,
            self._settings.mock_inputs_enabled,
            self._settings.claim_expiration_maintenance_enabled,
            self._settings.cloud_sync_enabled,
            self._settings.cloud_sync_base_url,
            self._settings.finder_recording_modes,
            self._settings.position_roi_snapshot_enabled,
            self._settings.ocr_profiling_enabled,
        )

        self._sub_cloud_sync = self._components.persisted_events.subscribe(
            self._on_persisted_event_for_cloud_sync
        )

        self._supervisor.start_thread(
            name="db_writer",
            target=self._components.db_writer_worker.run,
            worker_kwargs={"stop_event": self._stop_event},
        )

        self._supervisor.start_thread(
            name="cloud_sync",
            target=self._components.cloud_sync_worker.run,
            worker_kwargs={"stop_event": self._stop_event},
        )

        self._supervisor.start_thread(
            name="input_coordinator",
            target=self._components.input_coordinator.run,
            worker_kwargs={"stop_event": self._stop_event},
        )

        if self._settings.claim_expiration_maintenance_enabled:
            self._supervisor.start_thread(
                name="claim_expiration_maintenance",
                target=self._run_claim_expiration_maintenance,
                worker_kwargs={"stop_event": self._stop_event},
            )

        self._supervisor.start_thread(
            name="chat_tail",
            target=start_chat_input,
            worker_kwargs={
                "path": self._settings.chat_log_path,
                "signal_sink": self._components.pending_inputs.emit,
                "stop_event": self._stop_event,
                "start_at_end": self._settings.chat_start_at_end,
            },
        )

        self._components.ocr_input_source.start(stop_event=self._stop_event)

        if self._settings.mock_inputs_enabled:
            self._supervisor.start_thread(
                name="mock_mining_input",
                target=start_mock_mining_input,
                worker_kwargs={
                    "signal_sink": self._components.pending_inputs.emit,
                    "stop_event": self._stop_event,
                    "interval_ms": self._settings.mock_mining_interval_ms,
                },
            )

        if self._sse_hub is not None:
            self._sub_sse = self._components.persisted_events.subscribe(self._sse_hub.on_envelope)

    def _on_persisted_event_for_cloud_sync(self, envelope: EventEnvelope) -> None:
        if envelope.event_type in _CLOUD_SYNC_WAKE_EVENT_TYPES:
            self._components.cloud_sync_worker.request_sync()

    def _run_claim_expiration_maintenance(self, *, stop_event: threading.Event) -> None:
        interval_s = max(1.0, self._settings.claim_expiration_maintenance_interval_s)
        logger.info("claim_expiration_maintenance_started interval_s=%s", interval_s)
        while not stop_event.is_set():
            now_ts_ms = time.time_ns() // 1_000_000
            request = RuntimeCommandRequest(ExpireMiningClaimsCommand(now_ts_ms=now_ts_ms))
            try:
                self._components.pending_inputs.emit(request)
                expired_count = request.result(timeout_s=10.0)
                pending_request = RuntimeCommandRequest(
                    ResolvePendingDropResultsCommand(now_ts_ms=now_ts_ms)
                )
                self._components.pending_inputs.emit(pending_request)
                resolved_drop_count = pending_request.result(timeout_s=10.0)
            except ChannelClosedError:
                if stop_event.is_set():
                    break
                logger.exception("claim_expiration_maintenance_channel_closed")
            except Exception:
                if stop_event.is_set():
                    break
                logger.exception("claim_expiration_maintenance_failed")
            else:
                if expired_count:
                    logger.info(
                        "claim_expiration_maintenance_expired count=%s now_ts_ms=%s",
                        expired_count,
                        now_ts_ms,
                    )
                if resolved_drop_count:
                    logger.info(
                        "claim_expiration_maintenance_resolved_pending_drops count=%s now_ts_ms=%s",
                        resolved_drop_count,
                        now_ts_ms,
                    )
            stop_event.wait(interval_s)
        logger.info("claim_expiration_maintenance_stopped")

    def stop(self) -> None:
        if not self._started:
            return
        logger.info("app_stopping")
        self._stop_event.set()
        self._components.cloud_sync_worker.request_sync()

        if self._sub_sse is not None:
            self._sub_sse.close()
            self._sub_sse = None
        if self._sub_cloud_sync is not None:
            self._sub_cloud_sync.close()
            self._sub_cloud_sync = None

        self._supervisor.join_thread("chat_tail")
        self._components.ocr_input_source.stop()
        self._supervisor.join_thread("mock_mining_input")
        self._supervisor.join_thread("claim_expiration_maintenance")
        self._supervisor.join_thread("cloud_sync")

        self._components.pending_inputs.close()
        self._supervisor.join_thread("input_coordinator")

        self._components.pending_db_commands.close()
        self._components.pending_events.close()
        self._supervisor.join_thread("db_writer")
        self._started = False
        logger.info("app_stopped")
