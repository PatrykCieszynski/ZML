from __future__ import annotations

import threading
import time
from datetime import datetime

from zml_game_bridge.events.base import EventBase, should_persist_event
from zml_game_bridge.events.bus import PersistedEventBus
from zml_game_bridge.events.envelope import EventEnvelope
from zml_game_bridge.events.serialization import event_payload_json
from zml_game_bridge.runtime.event_queue import EventChannel
from zml_game_bridge.runtime.message_processor import (
    NoOpRuntimeMessageProcessor,
    RuntimeMessageProcessor,
)


class RuntimeMessageWorker:
    """
    Sequential coordinator for input messages before persistence.

    Input threads can emit both durable events and transient signals here.
    Domain processors may derive durable events from those messages. Only
    durable events are forwarded to the DB writer.
    """

    def __init__(
        self,
        *,
        pending_messages: EventChannel,
        pending_events: EventChannel,
        live_events: PersistedEventBus,
        message_processor: RuntimeMessageProcessor | None = None,
    ) -> None:
        self.pending_messages = pending_messages
        self.pending_events = pending_events
        self.live_events = live_events
        self.message_processor = message_processor or NoOpRuntimeMessageProcessor()
        self._next_transient_event_id = -1

    def run(self, *, stop_event: threading.Event) -> None:
        while not stop_event.is_set() or self.pending_messages.size() > 0:
            message = self.pending_messages.take(timeout_s=0.1)
            if message is None:
                continue

            derived_messages = list(self.message_processor.process(message))

            self._route_message(message)
            for derived_message in derived_messages:
                self._route_message(derived_message)

    def _route_message(self, message: EventBase) -> None:
        if should_persist_event(message):
            self.pending_events.emit(message)
        else:
            self.live_events.publish(self._transient_event_envelope(message))

    def _transient_event_envelope(self, event: EventBase) -> EventEnvelope:
        event_dt_obj = getattr(event, "event_dt", None)
        event_dt = event_dt_obj.isoformat() if isinstance(event_dt_obj, datetime) else None
        event_id = self._next_transient_event_id
        self._next_transient_event_id -= 1
        return EventEnvelope(
            event_id=event_id,
            created_ts_ms=time.time_ns() // 1_000_000,
            event_dt=event_dt,
            event_type=type(event).__name__,
            payload_json=event_payload_json(event),
        )
