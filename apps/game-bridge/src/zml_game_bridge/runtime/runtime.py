from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from zml_game_bridge.api.channels.position_hub import PositionHub
from zml_game_bridge.api.channels.sse_hub import SseHub
from zml_game_bridge.application.mining.claims.commands import ExpireMiningClaimsCommand
from zml_game_bridge.application.mining.equipment.service import MiningEquipmentService
from zml_game_bridge.application.mining.segments.session import RunSessionService
from zml_game_bridge.application.position.model import PositionSnapshot
from zml_game_bridge.application.position.tracking import PositionTrackingService
from zml_game_bridge.inputs.chat.runner import start_chat_input
from zml_game_bridge.inputs.mock.mining import start_mock_mining_input
from zml_game_bridge.inputs.ocr.pipelines.position.model import OcrPosition
from zml_game_bridge.inputs.ocr.runner import start_ocr_input
from zml_game_bridge.inputs.ocr.tesserocr_runtime import preload_tesserocr
from zml_game_bridge.runtime.bootstrap import RuntimeComponents
from zml_game_bridge.runtime.channels import ChannelClosedError
from zml_game_bridge.runtime.db_commands import DbCommand
from zml_game_bridge.runtime.runtime_commands import RuntimeCommand, RuntimeCommandRequest
from zml_game_bridge.runtime.supervisor import WorkerSupervisor
from zml_game_bridge.settings import Settings

logger = logging.getLogger(__name__)


class AppRuntime:
    def __init__(
        self,
        *,
        settings: Settings,
        components: RuntimeComponents,
        supervisor: WorkerSupervisor,
        sse_hub: SseHub | None = None,
        position_hub: PositionHub | None = None,
    ) -> None:
        self._settings = settings
        self._components = components
        self._supervisor = supervisor
        self._stop_event = threading.Event()
        self._sub_sse = None
        self._sse_hub = sse_hub
        self._position_hub = position_hub
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
            "claim_expiration_maintenance_enabled=%s finder_recording_modes=%s "
            "position_roi_snapshot_enabled=%s ocr_profiling_enabled=%s",
            self._settings.db_path,
            self._settings.chat_log_path,
            self._settings.mining_resource_catalog_path,
            self._settings.mining_tools_path,
            self._settings.ocr_profile_path,
            self._settings.ocr_enabled,
            self._settings.mock_inputs_enabled,
            self._settings.claim_expiration_maintenance_enabled,
            self._settings.finder_recording_modes,
            self._settings.position_roi_snapshot_enabled,
            self._settings.ocr_profiling_enabled,
        )

        self._supervisor.start_thread(
            name="db_writer",
            target=self._components.db_writer_worker.run,
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

        if self._settings.ocr_enabled:
            try:
                # Needed for 'tesserocr import failed: signal only works in main thread of the main interpreter'
                preload_tesserocr()
            except Exception as exc:
                self._supervisor.mark_crashed("ocr_worker", exc)
                raise

            self._supervisor.start_thread(
                name="ocr_worker",
                target=start_ocr_input,
                worker_kwargs={
                    "position_sink": self._on_position,
                    "signal_sink": self._components.pending_inputs.emit,
                    "stop_event": self._stop_event,
                    "roi_profile_path": self._settings.ocr_profile_path,
                    "finder_recording_modes": self._settings.finder_recording_modes,
                    "finder_recording_dir": self._settings.finder_recording_dir,
                    "finder_recording_interval_s": self._settings.finder_recording_interval_s,
                    "finder_recording_max_samples": self._settings.finder_recording_max_samples,
                    "finder_presence_check_enabled": (self._settings.finder_presence_check_enabled),
                    "position_roi_snapshot_enabled": self._settings.position_roi_snapshot_enabled,
                    "position_roi_snapshot_dir": self._settings.position_roi_snapshot_dir,
                    "position_roi_snapshot_interval_s": (
                        self._settings.position_roi_snapshot_interval_s
                    ),
                    "position_roi_snapshot_max_samples": (
                        self._settings.position_roi_snapshot_max_samples
                    ),
                    "ocr_profiling_enabled": self._settings.ocr_profiling_enabled,
                    "ocr_profiling_interval_s": self._settings.ocr_profiling_interval_s,
                },
            )

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

    def _on_position(self, position: OcrPosition) -> None:
        self._components.position_service.ingest_snapshot(
            PositionSnapshot(
                observed_ts_ms=position.ts_ms,
                received_ts_ms=time.time_ns() // 1_000_000,
                position=position.position,
                source="ocr",
            )
        )

    def _run_claim_expiration_maintenance(self, *, stop_event: threading.Event) -> None:
        interval_s = max(1.0, self._settings.claim_expiration_maintenance_interval_s)
        logger.info("claim_expiration_maintenance_started interval_s=%s", interval_s)
        while not stop_event.is_set():
            now_ts_ms = time.time_ns() // 1_000_000
            request = RuntimeCommandRequest(ExpireMiningClaimsCommand(now_ts_ms=now_ts_ms))
            try:
                self._components.pending_inputs.emit(request)
                expired_count = request.result(timeout_s=10.0)
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
            stop_event.wait(interval_s)
        logger.info("claim_expiration_maintenance_stopped")

    def stop(self) -> None:
        if not self._started:
            return
        logger.info("app_stopping")
        self._stop_event.set()

        if self._sub_sse is not None:
            self._sub_sse.close()
            self._sub_sse = None

        self._supervisor.join_thread("chat_tail")
        self._supervisor.join_thread("ocr_worker")
        self._supervisor.join_thread("mock_mining_input")
        self._supervisor.join_thread("claim_expiration_maintenance")

        self._components.pending_inputs.close()
        self._supervisor.join_thread("input_coordinator")

        self._components.pending_db_commands.close()
        self._components.pending_events.close()
        self._supervisor.join_thread("db_writer")
        self._started = False
        logger.info("app_stopped")
