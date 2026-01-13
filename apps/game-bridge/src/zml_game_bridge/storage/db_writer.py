from __future__ import annotations

import threading
from pathlib import Path

from zml_game_bridge.app.event_channel import EventChannel
from zml_game_bridge.events.bus import PersistedEventBus
from zml_game_bridge.storage.event_store import EventStore


class DbWriter:
    db_path: Path
    gateway: EventChannel
    bus: PersistedEventBus

    def __init__(self, *, db_path: Path, gateway: EventChannel, bus: PersistedEventBus) -> None:
        self.db_path = db_path
        self.gateway = gateway
        self.bus = bus

    def run(self, *, stop_event: threading.Event) -> None:
        event_store = EventStore(self.db_path)
        event_store.open()
        try:
            while not stop_event.is_set():
                event = self.gateway.take(timeout_s=0.1)
                if event is None:
                    continue

                # TODO: Decide policy on DB failure:
                # - retry? (how many times)
                # - drop event? (metrics)
                # - stop whole runtime? (fail-fast)
                # Also: log exceptions with enough context (event_type).
                event_envelope = event_store.append(event)
                self.bus.publish(event_envelope)
        finally:
            event_store.close()