from __future__ import annotations

import threading
from threading import Thread
from pathlib import Path

from zml_game_bridge.api.sse_hub import SseHub
from zml_game_bridge.api.ws_hub import OcrPositionHub
from zml_game_bridge.app.event_channel import EventChannel
from zml_game_bridge.inputs.ocr.runner import start_ocr_input
from zml_game_bridge.storage.db_writer import DbWriter
from zml_game_bridge.events.in_memory_persisted_event_bus import (
    InMemoryPersistedEventBus,
)
from zml_game_bridge.inputs.chat.runner import start_chat_input

class AppRuntime:
    def __init__(self, *, db_path: Path, chat_log_path: Path | None) -> None:
        self._db_path = db_path
        self._chat_log_path = chat_log_path

        self._stop_event = threading.Event()
        self._bus = InMemoryPersistedEventBus()
        self._gateway = EventChannel()
        self._db_writer = DbWriter(db_path=self._db_path, gateway=self._gateway, bus=self._bus)

        self._t_db: Thread | None = None
        self._t_chat: Thread | None = None
        self._t_ocr: Thread | None = None

        self._sub_print = None
        self._sub_sse = None

        self._sse_hub: SseHub | None = None
        self._position_hub: OcrPositionHub | None = None

    @property
    def position_hub(self) -> OcrPositionHub:
        if self._position_hub is None:
            raise RuntimeError("Position hub not attached")
        return self._position_hub

    def attach_sse_hub(self, hub: SseHub) -> None:
        self._sse_hub = hub

    def attach_position_hub(self, hub: OcrPositionHub) -> None:
        self._position_hub = hub


    def start(self) -> None:
        # TODO: idempotency guard (if already started -> return)

        hub = self.position_hub

        self._t_db = Thread(
            target=self._db_writer.run,
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
                "event_sink": self._gateway.emit,
                "stop_event": self._stop_event,
                "start_at_end": True,
            },
            daemon=True,
        )
        self._t_chat.start()


        self._t_ocr = Thread(
            target=start_ocr_input,
            kwargs={
                "position_sink": hub.publish_threadsafe,
                "stop_event": self._stop_event,
            },
            daemon=True,
        )
        self._t_ocr.start()

        self._sub_print = self._bus.subscribe(lambda env: print(f"New event stored: {env}"))

        # SSE fan-out (if attached)
        if self._sse_hub is not None:
            self._sub_sse = self._bus.subscribe(self._sse_hub.on_envelope)

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
        if self._t_db is not None:
            self._t_db.join(timeout=2.0)
        if self._t_ocr is not None:
            self._t_ocr.join(timeout=2.0)
