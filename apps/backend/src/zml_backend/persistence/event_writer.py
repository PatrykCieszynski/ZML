from __future__ import annotations

import sqlite3

from zml_backend.events.base import EventBase, should_persist_event
from zml_backend.events.envelope import EventEnvelope
from zml_backend.persistence.event_projector import EventProjector, NoOpEventProjector
from zml_backend.persistence.events import EventStore


class EventWriter:
    """
    Writes one event and its projections in a single SQLite transaction.

    Live fan-out is intentionally outside this class. Callers should publish
    the returned envelope only after write() succeeds.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        projector: EventProjector | None = None,
    ) -> None:
        self._conn = conn
        self._event_store = EventStore(conn)
        self._projector = projector or NoOpEventProjector()

    def write(self, event: EventBase) -> EventEnvelope:
        if not should_persist_event(event):
            raise ValueError(f"Refusing to persist transient event: {type(event).__name__}")
        with self._conn:
            event_envelope = self._event_store.append(event)
            self._projector.project(
                conn=self._conn,
                event=event,
                envelope=event_envelope,
            )
        return event_envelope
