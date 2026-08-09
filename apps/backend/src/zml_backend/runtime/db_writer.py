from __future__ import annotations

import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any

from zml_backend.events.bus import PersistedEventBus
from zml_backend.persistence.event_projector import EventProjector
from zml_backend.persistence.event_writer import EventWriter
from zml_backend.persistence.schema import ensure_schema
from zml_backend.persistence.sqlite import open_writer_connection
from zml_backend.runtime.channels import ChannelClosed, EventChannel
from zml_backend.runtime.db_commands import DbCommandChannel, DbCommandRequest
from zml_backend.runtime.event_requests import EventWriteRequest

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
        pending_commands: DbCommandChannel | None = None,
    ) -> None:
        self.db_path = db_path
        self.pending_events = pending_events
        self.persisted_events = persisted_events
        self.projector = projector
        self.pending_commands = pending_commands
        self.conn: sqlite3.Connection | None = None

    def open(self) -> None:
        self.conn = open_writer_connection(self.db_path)

    def close(self) -> None:
        conn = self.conn
        if conn is not None:
            conn.close()
            self.conn = None

    def run(self, *, stop_event: threading.Event) -> None:
        # Runtime closes both DB channels when no more work can arrive.
        _ = stop_event
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
            events_open = True
            commands_open = self.pending_commands is not None
            while events_open or commands_open:
                command = self._take_command(timeout_s=0.0 if events_open else 0.1)
                if isinstance(command, ChannelClosed):
                    commands_open = False
                    continue
                if command is not None:
                    self._execute_command(command)
                    continue

                if not events_open:
                    continue

                item = self.pending_events.take(timeout_s=0.1)
                if isinstance(item, ChannelClosed):
                    events_open = False
                    continue
                if item is None:
                    continue
                event = item.event if isinstance(item, EventWriteRequest) else item

                # TODO: Decide policy on DB failure:
                # - retry? (how many times)
                # - drop event? (metrics)
                # - stop whole runtime? (fail-fast)
                # Also: log exceptions with enough context (event_type).

                # TODO batching?
                current_event_type = type(event).__name__
                try:
                    event_envelope = event_writer.write(event)
                except Exception as exc:
                    if isinstance(item, EventWriteRequest):
                        item.set_exception(exc)
                    raise
                persisted_events_count += 1
                logger.debug(
                    "event_persisted event_id=%s event_type=%s",
                    event_envelope.event_id,
                    event_envelope.event_type,
                )
                current_event_type = None
                self.persisted_events.publish(event_envelope)
                if isinstance(item, EventWriteRequest):
                    item.set_result(event_envelope)
        except Exception:
            logger.exception("db_writer_crashed current_event_type=%s", current_event_type)
            raise
        finally:
            logger.info("db_writer_stopped persisted_events=%s", persisted_events_count)
            self.close()

    def _take_command(self, *, timeout_s: float) -> DbCommandRequest[Any] | ChannelClosed | None:
        if self.pending_commands is None:
            return None
        return self.pending_commands.take(timeout_s=timeout_s)

    def _execute_command(self, request: DbCommandRequest[Any]) -> None:
        if self.conn is None:
            request.set_exception(RuntimeError("DB writer connection is not open"))
            return
        try:
            with self.conn:
                result = request.command.execute(self.conn)
        except Exception as exc:
            logger.exception("db_command_failed command_type=%s", type(request.command).__name__)
            request.set_exception(exc)
        else:
            logger.debug("db_command_executed command_type=%s", type(request.command).__name__)
            request.set_result(result)
