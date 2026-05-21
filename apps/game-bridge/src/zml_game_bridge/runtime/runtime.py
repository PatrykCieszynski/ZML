from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from threading import Thread

from zml_game_bridge.api.channels.position_hub import OcrPositionHub
from zml_game_bridge.api.channels.sse_hub import SseHub
from zml_game_bridge.domain.mining_cost import MiningEquipmentProfile
from zml_game_bridge.domain.position import WorldPos
from zml_game_bridge.events.in_memory_persisted_event_bus import (
    InMemoryPersistedEventBus,
)
from zml_game_bridge.inputs.chat.runner import start_chat_input
from zml_game_bridge.inputs.mock.mining import start_mock_mining_input
from zml_game_bridge.inputs.ocr.pipelines.position.model import OcrPosition
from zml_game_bridge.inputs.ocr.runner import start_ocr_input
from zml_game_bridge.persistence.event_projector import CompositeEventProjector
from zml_game_bridge.persistence.mining_claims import MiningClaimProjector, MiningClaimReader
from zml_game_bridge.persistence.mining_drops import MiningDropProjector
from zml_game_bridge.persistence.runs import RunSegmentProjector
from zml_game_bridge.persistence.schema import ensure_schema
from zml_game_bridge.persistence.sqlite import open_sqlite
from zml_game_bridge.resources.mining_resources import MiningResourceCatalog
from zml_game_bridge.runtime.channels import EventChannel, SignalChannel
from zml_game_bridge.runtime.db_writer import DbWriterWorker
from zml_game_bridge.runtime.input_coordinator import InputCoordinator
from zml_game_bridge.runtime.mining import MiningCoordinator
from zml_game_bridge.runtime.mining.claim_lifecycle import ActiveClaim
from zml_game_bridge.runtime.mining.run_session import RunSessionService
from zml_game_bridge.runtime.mining.settings import default_id_factory
from zml_game_bridge.runtime.mining.tools import MiningToolService
from zml_game_bridge.runtime.position_state import LatestPositionState

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
        self._pending_signals = SignalChannel()
        self._pending_events = EventChannel()
        self._persisted_events = InMemoryPersistedEventBus()
        self._latest_position = LatestPositionState()
        self._resource_catalog = MiningResourceCatalog(user_path=self._mining_resource_catalog_path)
        self._mining_tool_service = MiningToolService(path=self._mining_tools_path)
        self._run_session_service = RunSessionService(
            db_path=self._db_path,
            id_factory=default_id_factory,
        )
        self._mining_coordinator = MiningCoordinator(
            profile_provider=self._mining_tool_service.get_equipment_profile,
            position_provider=self._current_position,
            resource_catalog=self._resource_catalog,
            run_context_provider=self._run_context_for_drop,
        )
        self._input_coordinator = InputCoordinator(
            pending_signals=self._pending_signals,
            pending_events=self._pending_events,
            signal_processor=self._mining_coordinator,
        )
        self._db_writer_worker = DbWriterWorker(
            db_path=self._db_path,
            pending_events=self._pending_events,
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
    def mining_tool_service(self) -> MiningToolService:
        return self._mining_tool_service

    @property
    def run_session_service(self) -> RunSessionService:
        return self._run_session_service

    def attach_sse_hub(self, hub: SseHub) -> None:
        self._sse_hub = hub

    def attach_position_hub(self, hub: OcrPositionHub) -> None:
        self._position_hub = hub

    def start(self) -> None:
        if self._started:
            return
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

        self._t_input = Thread(
            target=self._input_coordinator.run,
            kwargs={"stop_event": self._stop_event},
            daemon=True,
        )
        self._t_input.start()

        self._t_db = Thread(
            target=self._db_writer_worker.run,
            kwargs={"stop_event": self._stop_event},
            daemon=True,
        )
        self._t_db.start()

        if self._chat_log_path is None:
            raise RuntimeError("Chat log path is not set; cannot start chat input")

        self._t_chat = Thread(
            target=start_chat_input,
            kwargs={
                "path": self._chat_log_path,
                "signal_sink": self._pending_signals.emit,
                "stop_event": self._stop_event,
                "start_at_end": self._chat_start_at_end,
            },
            daemon=True,
        )
        self._t_chat.start()

        if self._ocr_enabled:
            self._t_ocr = Thread(
                target=start_ocr_input,
                kwargs={
                    "position_sink": self._on_position,
                    "signal_sink": self._pending_signals.emit,
                    "stop_event": self._stop_event,
                },
                daemon=True,
            )
            self._t_ocr.start()

        if self._mock_inputs_enabled:
            self._t_mock = Thread(
                target=start_mock_mining_input,
                kwargs={
                    "signal_sink": self._pending_signals.emit,
                    "stop_event": self._stop_event,
                    "interval_ms": self._mock_mining_interval_ms,
                },
                daemon=True,
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
        conn = open_sqlite(self._db_path)
        try:
            ensure_schema(conn)
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
        logger.info("app_stopping")
        self._stop_event.set()

        if self._sub_sse is not None:
            self._sub_sse.close()
            self._sub_sse = None

        if self._t_chat is not None:
            self._t_chat.join(timeout=2.0)
        if self._t_ocr is not None:
            self._t_ocr.join(timeout=2.0)
        if self._t_mock is not None:
            self._t_mock.join(timeout=2.0)
        if self._t_input is not None:
            self._t_input.join(timeout=2.0)
        if self._t_db is not None:
            self._t_db.join(timeout=2.0)
        self._started = False
        logger.info("app_stopped")


def _now_ms() -> int:
    return time.time_ns() // 1_000_000
