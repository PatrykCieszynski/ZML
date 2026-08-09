from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from collections.abc import Sequence

from zml_backend.events.base import EventBase
from zml_backend.events.envelope import EventEnvelope


class EventProjector(ABC):
    """
    Applies durable read-model updates derived from a persisted event.

    Projectors are called inside the EventWriter transaction. If a projector fails,
    the event insert is rolled back and the event is not published to downstream
    live subscribers.
    """

    @abstractmethod
    def project(
        self,
        *,
        conn: sqlite3.Connection,
        event: EventBase,
        envelope: EventEnvelope,
    ) -> None: ...


class NoOpEventProjector(EventProjector):
    def project(
        self,
        *,
        conn: sqlite3.Connection,
        event: EventBase,
        envelope: EventEnvelope,
    ) -> None:
        _ = (conn, event, envelope)


class CompositeEventProjector(EventProjector):
    def __init__(self, projectors: Sequence[EventProjector]) -> None:
        self._projectors = tuple(projectors)

    def project(
        self,
        *,
        conn: sqlite3.Connection,
        event: EventBase,
        envelope: EventEnvelope,
    ) -> None:
        for projector in self._projectors:
            projector.project(conn=conn, event=event, envelope=envelope)
