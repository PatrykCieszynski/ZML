from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Any

from zml_backend.events.base import EventBase, should_persist_event
from zml_backend.events.bus import PersistedEventBus
from zml_backend.events.envelope import EventEnvelope
from zml_backend.events.serialization import event_payload_json
from zml_backend.runtime.channels import ChannelClosed, EventChannel, RuntimeInputChannel
from zml_backend.runtime.event_requests import EventWriteRequest
from zml_backend.runtime.input_processor import InputProcessor, NoOpInputProcessor
from zml_backend.runtime.runtime_commands import RuntimeCommandRequest

logger = logging.getLogger(__name__)


class InputCoordinator:
    """
    Sequential boundary between input threads and durable event persistence.

    Input threads and API routes emit normalized inputs into RuntimeInputChannel.
    Input processors, such as MiningCoordinator, may derive durable domain
    events or synchronous command responses. Only durable events are forwarded
    to EventChannel for the DB writer.
    """

    def __init__(
        self,
        *,
        pending_inputs: RuntimeInputChannel,
        pending_events: EventChannel,
        input_processor: InputProcessor | None = None,
        live_events: PersistedEventBus | None = None,
        command_persist_timeout_s: float = 5.0,
    ) -> None:
        self.pending_inputs = pending_inputs
        self.pending_events = pending_events
        self.input_processor = input_processor or NoOpInputProcessor()
        self.live_events = live_events
        self.command_persist_timeout_s = command_persist_timeout_s

    def run(self, *, stop_event: threading.Event) -> None:
        # Producers observe stop_event; this worker exits only after the input channel is closed.
        _ = stop_event
        processed_inputs = 0
        while True:
            item = self.pending_inputs.take(timeout_s=0.1)
            if isinstance(item, ChannelClosed):
                break
            if item is None:
                continue
            processed_inputs += 1
            if isinstance(item, RuntimeCommandRequest):
                self._process_command(item)
                continue

            signal = item
            logger.debug("signal_received signal_type=%s", type(signal).__name__)
            derived_events = list(self.input_processor.process_signal(signal))
            if not derived_events:
                logger.debug("signal_ignored signal_type=%s", type(signal).__name__)
                continue

            logger.debug(
                "signal_processed signal_type=%s derived_events=%s",
                type(signal).__name__,
                [type(event).__name__ for event in derived_events],
            )

            for event in derived_events:
                self._route_event(event)
        logger.info("input_coordinator_stopped processed_inputs=%s", processed_inputs)

    def _process_command(self, request: RuntimeCommandRequest[Any]) -> None:
        command_type = type(request.command).__name__
        try:
            logger.debug("runtime_command_received command_type=%s", command_type)
            result = self.input_processor.process_command(request.command)
            for event in result.events:
                self._route_event(event, wait=True)
        except Exception as exc:
            logger.exception("runtime_command_failed command_type=%s", command_type)
            request.set_exception(exc)
        else:
            logger.debug("runtime_command_processed command_type=%s", command_type)
            request.set_result(result.value)

    def _route_event(self, event: EventBase, *, wait: bool = False) -> None:
        if should_persist_event(event):
            logger.debug("durable_event_routed event_type=%s", type(event).__name__)
            if wait:
                request = EventWriteRequest(event)
                self.pending_events.emit(request)
                request.result(timeout_s=self.command_persist_timeout_s)
            else:
                self.pending_events.emit(event)
            return

        if self.live_events is not None:
            logger.debug("transient_event_published event_type=%s", type(event).__name__)
            self.live_events.publish(_transient_envelope(event))


def _transient_envelope(event: EventBase) -> EventEnvelope:
    event_dt_obj = getattr(event, "event_dt", None)
    event_dt = event_dt_obj.isoformat() if isinstance(event_dt_obj, datetime) else None
    return EventEnvelope(
        event_id=0,
        created_ts_ms=time.time_ns() // 1_000_000,
        event_dt=event_dt,
        event_type=type(event).__name__,
        payload_json=event_payload_json(event),
    )
