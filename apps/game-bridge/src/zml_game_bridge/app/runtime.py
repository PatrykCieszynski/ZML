from __future__ import annotations

import threading
from threading import Thread
from pathlib import Path

from zml_game_bridge.app.event_gateway import EventGateway
from zml_game_bridge.storage.db_writer import DbWriter
from zml_game_bridge.events.bus_in_memory import InMemoryEventBus
from zml_game_bridge.inputs.chat.runner import start_chat_input

class AppRuntime:
    def __init__(self, *, db_path: Path, chat_log_path: Path | None) -> None:
        self._db_path = db_path
        self._chat_log_path = chat_log_path

        self._stop_event = threading.Event()
        self._bus = InMemoryEventBus()
        self._gateway = EventGateway()
        self._db_writer = DbWriter(db_path=self._db_path, gateway=self._gateway, bus=self._bus)

        self._t_db: Thread | None = None
        self._t_chat: Thread | None = None
        self._sub = None

    def start(self) -> None:
        # TODO: idempotency guard (if already started -> return)
        self._t_db = Thread(target=self._db_writer.run, kwargs={"stop_event": self._stop_event}, daemon=True)
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

        self._t_db.start()
        self._t_chat.start()

        self._sub = self._bus.subscribe(lambda env: print(f"New event stored: {env}"))

    def stop(self) -> None:
        self._stop_event.set()

        if self._sub is not None:
            self._sub.close()
            self._sub = None

        if self._t_chat is not None:
            self._t_chat.join(timeout=2.0)
        if self._t_db is not None:
            self._t_db.join(timeout=2.0)
