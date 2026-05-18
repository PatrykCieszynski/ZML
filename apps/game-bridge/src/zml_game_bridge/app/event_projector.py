from __future__ import annotations

import sqlite3
from typing import Protocol

from zml_game_bridge.events.base import EventBase
from zml_game_bridge.events.envelope import EventEnvelope


class EventProjector(Protocol):
    """
    Applies durable read-model updates derived from a persisted event.

    Projectors are called inside the DB writer transaction. If a projector fails,
    the event insert is rolled back and the event is not published to downstream
    live subscribers.
    """

    def project(
        self,
        *,
        conn: sqlite3.Connection,
        event: EventBase,
        envelope: EventEnvelope,
    ) -> None:
        ...


class NoOpEventProjector:
    def project(
        self,
        *,
        conn: sqlite3.Connection,
        event: EventBase,
        envelope: EventEnvelope,
    ) -> None:
        _ = (conn, event, envelope)
