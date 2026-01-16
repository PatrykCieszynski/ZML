from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from zml_game_bridge.app.event_channel import EventChannel
from zml_game_bridge.events.bus import PersistedEventBus
from zml_game_bridge.storage.db_schema import ensure_schema
from zml_game_bridge.storage.event_store import EventStore
from zml_game_bridge.storage.sqlite import open_sqlite


class DbWriterWorker:
    db_path: Path
    gateway: EventChannel
    bus: PersistedEventBus

    def __init__(self, *, db_path: Path, gateway: EventChannel, bus: PersistedEventBus) -> None:
        self.db_path = db_path
        self.gateway = gateway
        self.bus = bus
        self.conn: sqlite3.Connection | None = None

    def open(self) -> None:
        self.conn = open_sqlite(self.db_path)

    def close(self) -> None:
        conn = self.conn
        if conn is not None:
            conn.close()
            self.conn = None

    def run(self, *, stop_event: threading.Event) -> None:
        self.open()
        if self.conn is None:
            raise RuntimeError("Failed to open DB connection")
        try:
            ensure_schema(self.conn)
        except Exception:
            self.close()
            raise

        event_store = EventStore(self.conn)

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

                # TODO batching?
                event_envelope = event_store.append(event)
                self.bus.publish(event_envelope)
        finally:
            self.close()