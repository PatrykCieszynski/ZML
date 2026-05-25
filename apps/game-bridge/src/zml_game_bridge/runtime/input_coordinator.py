from __future__ import annotations

import logging
import threading
from typing import Any

from zml_game_bridge.events.base import EventBase, should_persist_event
from zml_game_bridge.runtime.channels import EventChannel, RuntimeInputChannel
from zml_game_bridge.runtime.event_requests import EventWriteRequest
from zml_game_bridge.runtime.runtime_commands import RuntimeCommandRequest
from zml_game_bridge.runtime.signal_processor import NoOpSignalProcessor, SignalProcessor

logger = logging.getLogger(__name__)


class InputCoordinator:
    """
    Sequential boundary between input threads and durable event persistence.

    Input threads and API routes emit normalized inputs into RuntimeInputChannel.
    Signal processors, such as MiningCoordinator, may derive durable domain
    events or synchronous command responses. Only durable events are forwarded
    to EventChannel for the DB writer.
    """

    def __init__(
        self,
        *,
        pending_signals: RuntimeInputChannel,
        pending_events: EventChannel,
        signal_processor: SignalProcessor | None = None,
        command_persist_timeout_s: float = 5.0,
    ) -> None:
        self.pending_signals = pending_signals
        self.pending_events = pending_events
        self.signal_processor = signal_processor or NoOpSignalProcessor()
        self.command_persist_timeout_s = command_persist_timeout_s

    def run(self, *, stop_event: threading.Event) -> None:
        while not stop_event.is_set() or self.pending_signals.size() > 0:
            item = self.pending_signals.take(timeout_s=0.1)
            if item is None:
                continue
            if isinstance(item, RuntimeCommandRequest):
                self._process_command(item)
                continue

            signal = item
            logger.debug("signal_received signal_type=%s", type(signal).__name__)
            derived_events = list(self.signal_processor.process(signal))
            if not derived_events:
                logger.debug("signal_ignored signal_type=%s", type(signal).__name__)
                continue

            logger.debug(
                "signal_processed signal_type=%s derived_events=%s",
                type(signal).__name__,
                [type(event).__name__ for event in derived_events],
            )

            for event in derived_events:
                self._route_durable_event(event)

    def _process_command(self, request: RuntimeCommandRequest[Any]) -> None:
        command_type = type(request.command).__name__
        try:
            logger.debug("runtime_command_received command_type=%s", command_type)
            result = self.signal_processor.process_command(request.command)
            for event in result.events:
                self._route_durable_event(event, wait=True)
        except Exception as exc:
            logger.exception("runtime_command_failed command_type=%s", command_type)
            request.set_exception(exc)
        else:
            logger.debug("runtime_command_processed command_type=%s", command_type)
            request.set_result(result.value)

    def _route_durable_event(self, event: EventBase, *, wait: bool = False) -> None:
        if should_persist_event(event):
            logger.debug("durable_event_routed event_type=%s", type(event).__name__)
            if wait:
                request = EventWriteRequest(event)
                self.pending_events.emit(request)
                request.result(timeout_s=self.command_persist_timeout_s)
            else:
                self.pending_events.emit(event)
