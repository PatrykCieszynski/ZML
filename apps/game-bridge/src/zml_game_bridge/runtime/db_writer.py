from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path

from zml_game_bridge.events.bus import PersistedEventBus
from zml_game_bridge.persistence.event_projector import EventProjector
from zml_game_bridge.persistence.event_writer import EventWriter
from zml_game_bridge.persistence.schema import ensure_schema
from zml_game_bridge.persistence.sqlite import open_sqlite
from zml_game_bridge.runtime.channels import EventChannel

logger = logging.getLogger(__name__)


class DbWriterWorker:
    db_path: Path
    pending_events: EventChannel
    persisted_events: PersistedEventBus

    def __init__(
        self,
        *,
        db_path: Path,
        pending_events: EventChannel,
        persisted_events: PersistedEventBus,
        projector: EventProjector | None = None,
    ) -> None:
        self.db_path = db_path
        self.pending_events = pending_events
        self.persisted_events = persisted_events
        self.projector = projector
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
        logger.info("db_writer_started db_path=%s", self.db_path)
        try:
            ensure_schema(self.conn)
        except Exception:
            self.close()
            raise

        event_writer = EventWriter(self.conn, projector=self.projector)
        persisted_events_count = 0
        current_event_type: str | None = None

        try:
            while not stop_event.is_set() or self.pending_events.size() > 0:
                event = self.pending_events.take(timeout_s=0.1)
                if event is None:
                    continue

                # TODO: Decide policy on DB failure:
                # - retry? (how many times)
                # - drop event? (metrics)
                # - stop whole runtime? (fail-fast)
                # Also: log exceptions with enough context (event_type).

                # TODO batching?
                current_event_type = type(event).__name__
                event_envelope = event_writer.write(event)
                persisted_events_count += 1
                logger.debug(
                    "event_persisted event_id=%s event_type=%s",
                    event_envelope.event_id,
                    event_envelope.event_type,
                )
                current_event_type = None
                self.persisted_events.publish(event_envelope)
        except Exception:
            logger.exception("db_writer_crashed current_event_type=%s", current_event_type)
            raise
        finally:
            logger.info("db_writer_stopped persisted_events=%s", persisted_events_count)
            self.close()
