from __future__ import annotations

import logging
import threading
from pathlib import Path
from threading import Thread

from zml_game_bridge.api.channels.position_hub import OcrPositionHub
from zml_game_bridge.api.channels.sse_hub import SseHub
from zml_game_bridge.events.envelope import EventEnvelope
from zml_game_bridge.events.in_memory_persisted_event_bus import (
    InMemoryPersistedEventBus,
)
from zml_game_bridge.inputs.chat.runner import start_chat_input
from zml_game_bridge.inputs.ocr.pipelines.position.model import OcrPosition
from zml_game_bridge.inputs.ocr.runner import start_ocr_input
from zml_game_bridge.runtime.db_writer import DbWriterWorker
from zml_game_bridge.runtime.event_queue import EventChannel
from zml_game_bridge.runtime.message_worker import RuntimeMessageWorker
from zml_game_bridge.runtime.mining_runtime_coordinator import MiningRuntimeCoordinator
from zml_game_bridge.runtime.position_state import LatestPositionState

logger = logging.getLogger(__name__)


class AppRuntime:
    def __init__(
        self,
        *,
        db_path: Path,
        chat_log_path: Path | None,
        chat_start_at_end: bool,
        ocr_enabled: bool,
    ) -> None:
        self._db_path = db_path
        self._chat_log_path = chat_log_path
        self._chat_start_at_end = chat_start_at_end
        self._ocr_enabled = ocr_enabled

        self._stop_event = threading.Event()
        self._pending_messages = EventChannel()
        self._pending_events = EventChannel()
        self._persisted_events = InMemoryPersistedEventBus()
        self._latest_position = LatestPositionState()
        self._mining_runtime_coordinator = MiningRuntimeCoordinator()
        self._message_worker = RuntimeMessageWorker(
            pending_messages=self._pending_messages,
            pending_events=self._pending_events,
            live_events=self._persisted_events,
            message_processor=self._mining_runtime_coordinator,
        )
        self._db_writer_worker = DbWriterWorker(
            db_path=self._db_path,
            pending_events=self._pending_events,
            persisted_events=self._persisted_events,
        )

        self._t_messages: Thread | None = None
        self._t_db: Thread | None = None
        self._t_chat: Thread | None = None
        self._t_ocr: Thread | None = None

        self._sub_print = None
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

    def attach_sse_hub(self, hub: SseHub) -> None:
        self._sse_hub = hub

    def attach_position_hub(self, hub: OcrPositionHub) -> None:
        self._position_hub = hub

    def start(self) -> None:
        if self._started:
            return
        self._started = True

        self._t_messages = Thread(
            target=self._message_worker.run,
            kwargs={"stop_event": self._stop_event},
            daemon=True,
        )
        self._t_messages.start()

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
                "event_sink": self._pending_messages.emit,
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
                    "signal_sink": self._pending_messages.emit,
                    "stop_event": self._stop_event,
                },
                daemon=True,
            )
            self._t_ocr.start()

        self._sub_print = self._persisted_events.subscribe(self._log_event_envelope)

        # SSE fan-out (if attached)
        if self._sse_hub is not None:
            self._sub_sse = self._persisted_events.subscribe(self._sse_hub.on_envelope)

    def _on_position(self, position: OcrPosition) -> None:
        self._latest_position.update(position)
        self.position_hub.publish_threadsafe(position)

    def _log_event_envelope(self, env: EventEnvelope) -> None:
        if env.event_id <= 0:
            logger.info("New transient event: %s", env)
        else:
            logger.info("New event stored: %s", env)

    def stop(self) -> None:
        self._stop_event.set()

        if self._sub_sse is not None:
            self._sub_sse.close()
            self._sub_sse = None

        if self._sub_print is not None:
            self._sub_print.close()
            self._sub_print = None

        if self._t_chat is not None:
            self._t_chat.join(timeout=2.0)
        if self._t_ocr is not None:
            self._t_ocr.join(timeout=2.0)
        if self._t_messages is not None:
            self._t_messages.join(timeout=2.0)
        if self._t_db is not None:
            self._t_db.join(timeout=2.0)
        self._started = False
