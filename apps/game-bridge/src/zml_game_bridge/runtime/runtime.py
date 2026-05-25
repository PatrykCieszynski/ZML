from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path
from threading import Thread
from typing import Any

from zml_game_bridge.api.channels.position_hub import OcrPositionHub
from zml_game_bridge.api.channels.sse_hub import SseHub
from zml_game_bridge.application.mining import MiningCoordinator
from zml_game_bridge.application.mining.claims.lifecycle import ActiveClaim
from zml_game_bridge.application.mining.equipment.service import MiningEquipmentService
from zml_game_bridge.application.mining.segments.session import RunSessionService
from zml_game_bridge.application.mining.settings import default_id_factory
from zml_game_bridge.application.position.latest_position import LatestPositionState
from zml_game_bridge.domain.mining_cost import MiningEquipmentProfile
from zml_game_bridge.domain.position import WorldPos
from zml_game_bridge.events.in_memory_persisted_event_bus import (
    InMemoryPersistedEventBus,
)
from zml_game_bridge.inputs.chat.runner import start_chat_input
from zml_game_bridge.inputs.mock.mining import start_mock_mining_input
from zml_game_bridge.inputs.ocr.pipelines.position.engine import preload_tesserocr
from zml_game_bridge.inputs.ocr.pipelines.position.model import OcrPosition
from zml_game_bridge.inputs.ocr.runner import start_ocr_input
from zml_game_bridge.persistence.event_projector import CompositeEventProjector
from zml_game_bridge.persistence.mining_claims import MiningClaimProjector, MiningClaimReader
from zml_game_bridge.persistence.mining_drops import MiningDropProjector
from zml_game_bridge.persistence.runs import RunSegmentProjector
from zml_game_bridge.persistence.schema import ensure_schema
from zml_game_bridge.persistence.sqlite import open_read_connection, open_writer_connection
from zml_game_bridge.resources.mining_resources import MiningResourceCatalog
from zml_game_bridge.runtime.channels import EventChannel, RuntimeInputChannel
from zml_game_bridge.runtime.db_commands import DbCommand, DbCommandChannel
from zml_game_bridge.runtime.db_writer import DbWriterWorker
from zml_game_bridge.runtime.input_coordinator import InputCoordinator
from zml_game_bridge.runtime.runtime_commands import RuntimeCommand, RuntimeCommandRequest
from zml_game_bridge.runtime.worker_health import WorkerHealthRegistry

logger = logging.getLogger(__name__)


class AppRuntime:
    def __init__(
        self,
        *,
        db_path: Path,
        chat_log_path: Path | None,
        mining_resource_catalog_path: Path,
        mining_tools_path: Path,
        chat_start_at_end: bool,
        ocr_enabled: bool,
        mock_inputs_enabled: bool,
        mock_mining_interval_ms: int,
    ) -> None:
        self._db_path = db_path
        self._chat_log_path = chat_log_path
        self._mining_resource_catalog_path = mining_resource_catalog_path
        self._mining_tools_path = mining_tools_path
        self._chat_start_at_end = chat_start_at_end
        self._ocr_enabled = ocr_enabled
        self._mock_inputs_enabled = mock_inputs_enabled
        self._mock_mining_interval_ms = mock_mining_interval_ms

        self._stop_event = threading.Event()
        self._worker_health = WorkerHealthRegistry()
        self._register_worker_health()
        self._pending_inputs = RuntimeInputChannel()
        self._pending_events = EventChannel()
        self._pending_db_commands = DbCommandChannel()
        self._persisted_events = InMemoryPersistedEventBus()
        self._latest_position = LatestPositionState()
        self._resource_catalog = MiningResourceCatalog(user_path=self._mining_resource_catalog_path)
        self._mining_equipment_service = MiningEquipmentService(path=self._mining_tools_path)
        self._run_session_service = RunSessionService(
            db_path=self._db_path,
            id_factory=default_id_factory,
        )
        self._mining_coordinator = MiningCoordinator(
            profile_provider=self._mining_equipment_service.get_equipment_profile,
            position_provider=self._current_position,
            resource_catalog=self._resource_catalog,
            run_context_provider=self._run_context_for_drop,
            db_command_executor=self.execute_db_command,
            mining_equipment_service=self._mining_equipment_service,
        )
        self._input_coordinator = InputCoordinator(
            pending_inputs=self._pending_inputs,
            pending_events=self._pending_events,
            input_processor=self._mining_coordinator,
        )
        self._db_writer_worker = DbWriterWorker(
            db_path=self._db_path,
            pending_events=self._pending_events,
            pending_commands=self._pending_db_commands,
            persisted_events=self._persisted_events,
            projector=CompositeEventProjector(
                [
                    RunSegmentProjector(),
                    MiningDropProjector(),
                    MiningClaimProjector(),
                ]
            ),
        )

        self._t_input: Thread | None = None
        self._t_db: Thread | None = None
        self._t_chat: Thread | None = None
        self._t_ocr: Thread | None = None
        self._t_mock: Thread | None = None

        self._sub_sse = None

        self._sse_hub: SseHub | None = None
        self._position_hub: OcrPositionHub | None = None
        self._started = False

    @property
    def db_path(self) -> Path:
        return self._db_path

    @property
    def position_hub(self) -> OcrPositionHub:
        if self._position_hub is None:
            raise RuntimeError("Position hub not attached")
        return self._position_hub

    @property
    def sse_hub(self) -> SseHub | None:
        return self._sse_hub

    @property
    def latest_position(self) -> LatestPositionState:
        return self._latest_position

    @property
    def mining_equipment_service(self) -> MiningEquipmentService:
        return self._mining_equipment_service

    @property
    def run_session_service(self) -> RunSessionService:
        return self._run_session_service

    def execute_db_command[T](self, command: DbCommand[T], *, timeout_s: float = 5.0) -> T:
        return self._pending_db_commands.execute(command, timeout_s=timeout_s)

    def health(self) -> dict[str, object]:
        return self._worker_health.as_dict()

    def execute_runtime_command[T](
        self,
        command: RuntimeCommand[T],
        *,
        timeout_s: float = 5.0,
    ) -> T:
        if self._stop_event.is_set():
            raise RuntimeError("Runtime is stopping")
        request = RuntimeCommandRequest(command)
        self._pending_inputs.emit(request)
        return request.result(timeout_s=timeout_s)

    def attach_sse_hub(self, hub: SseHub) -> None:
        self._sse_hub = hub

    def attach_position_hub(self, hub: OcrPositionHub) -> None:
        self._position_hub = hub

    def start(self) -> None:
        if self._started:
            return
        if self._pending_inputs.is_closed():
            raise RuntimeError("Runtime cannot be restarted after shutdown")
        if self._chat_log_path is None:
            raise RuntimeError("Chat log path is not set; cannot start chat input")
        self._stop_event.clear()
        self._restore_mining_lifecycle()
        self._started = True
        logger.info(
            "app_started db_path=%s chat_log_path=%s mining_resource_catalog_path=%s "
            "mining_tools_path=%s ocr_enabled=%s mock_inputs_enabled=%s",
            self._db_path,
            self._chat_log_path,
            self._mining_resource_catalog_path,
            self._mining_tools_path,
            self._ocr_enabled,
            self._mock_inputs_enabled,
        )

        self._t_db = self._create_worker_thread(
            name="db_writer",
            target=self._db_writer_worker.run,
            worker_kwargs={"stop_event": self._stop_event},
        )
        self._t_db.start()

        self._t_input = self._create_worker_thread(
            name="input_coordinator",
            target=self._input_coordinator.run,
            worker_kwargs={"stop_event": self._stop_event},
        )
        self._t_input.start()

        self._t_chat = self._create_worker_thread(
            name="chat_tail",
            target=start_chat_input,
            worker_kwargs={
                "path": self._chat_log_path,
                "signal_sink": self._pending_inputs.emit,
                "stop_event": self._stop_event,
                "start_at_end": self._chat_start_at_end,
            },
        )
        self._t_chat.start()

        if self._ocr_enabled:
            try:
                preload_tesserocr()  # Needed for 'tesserocr import failed: signal only works in main thread of the main interpreter'
            except Exception as exc:
                self._worker_health.mark_crashed("ocr_worker", exc)
                raise

            self._t_ocr = self._create_worker_thread(
                name="ocr_worker",
                target=start_ocr_input,
                worker_kwargs={
                    "position_sink": self._on_position,
                    "signal_sink": self._pending_inputs.emit,
                    "stop_event": self._stop_event,
                },
            )
            self._t_ocr.start()

        if self._mock_inputs_enabled:
            self._t_mock = self._create_worker_thread(
                name="mock_mining_input",
                target=start_mock_mining_input,
                worker_kwargs={
                    "signal_sink": self._pending_inputs.emit,
                    "stop_event": self._stop_event,
                    "interval_ms": self._mock_mining_interval_ms,
                },
            )
            self._t_mock.start()

        # SSE fan-out (if attached)
        if self._sse_hub is not None:
            self._sub_sse = self._persisted_events.subscribe(self._sse_hub.on_envelope)

    def _on_position(self, position: OcrPosition) -> None:
        self._latest_position.update(position)
        self.position_hub.publish_threadsafe(position)

    def _current_position(self) -> WorldPos | None:
        position = self._latest_position.get()
        return position.position if position is not None else None

    def _run_context_for_drop(self, observed_ts_ms: int, profile: MiningEquipmentProfile):
        return self._run_session_service.context_for_drop(
            observed_ts_ms=observed_ts_ms,
            profile=profile,
        )

    def _restore_mining_lifecycle(self) -> None:
        conn = open_writer_connection(self._db_path)
        try:
            ensure_schema(conn)
        finally:
            conn.close()

        conn = open_read_connection(self._db_path)
        try:
            rows = MiningClaimReader(conn).list_active(now_ts_ms=_now_ms())
        finally:
            conn.close()

        self._mining_coordinator.restore_active_claims(
            ActiveClaim(
                claim_id=row.claim_id,
                drop_id=row.drop_id,
                hit_id=row.hit_id,
                position=row.position,
                search_radius_m=row.search_radius_m,
            )
            for row in rows
        )

    def stop(self) -> None:
        if not self._started:
            return
        logger.info("app_stopping")
        self._stop_event.set()

        if self._sub_sse is not None:
            self._sub_sse.close()
            self._sub_sse = None

        self._join_thread(self._t_chat, "chat_tail")
        self._join_thread(self._t_ocr, "ocr_worker")
        self._join_thread(self._t_mock, "mock_mining_input")

        self._pending_inputs.close()
        self._join_thread(self._t_input, "input_coordinator")

        self._pending_db_commands.close()
        self._pending_events.close()
        self._join_thread(self._t_db, "db_writer")
        self._started = False
        logger.info("app_stopped")

    def _register_worker_health(self) -> None:
        self._worker_health.register("db_writer", enabled=True)
        self._worker_health.register("input_coordinator", enabled=True)
        self._worker_health.register("chat_tail", enabled=True)
        self._worker_health.register("ocr_worker", enabled=self._ocr_enabled)
        self._worker_health.register("mock_mining_input", enabled=self._mock_inputs_enabled)

    def _create_worker_thread(
        self,
        *,
        name: str,
        target: Callable[..., None],
        worker_kwargs: dict[str, Any],
    ) -> Thread:
        return Thread(
            target=self._run_worker,
            kwargs={"name": name, "target": target, "worker_kwargs": worker_kwargs},
            daemon=True,
        )

    def _run_worker(
        self,
        *,
        name: str,
        target: Callable[..., None],
        worker_kwargs: dict[str, Any],
    ) -> None:
        self._worker_health.mark_running(name)
        try:
            target(**worker_kwargs)
        except Exception as exc:
            self._worker_health.mark_crashed(name, exc)
            raise
        if self._stop_event.is_set():
            self._worker_health.mark_stopped(name)
        else:
            self._worker_health.mark_degraded(name, "worker returned before runtime shutdown")

    def _join_thread(self, thread: Thread | None, name: str) -> bool:
        if thread is None:
            return True
        thread.join(timeout=5.0)
        if thread.is_alive():
            logger.warning("runtime_thread_did_not_stop thread=%s", name)
            self._worker_health.mark_degraded(name, "worker did not stop within 5s")
            return False
        return True


def _now_ms() -> int:
    return time.time_ns() // 1_000_000
