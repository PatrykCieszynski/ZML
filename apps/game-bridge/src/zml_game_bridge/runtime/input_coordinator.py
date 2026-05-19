from __future__ import annotations

import threading

from zml_game_bridge.events.base import EventBase, should_persist_event
from zml_game_bridge.runtime.channels import EventChannel, SignalChannel
from zml_game_bridge.runtime.signal_processor import NoOpSignalProcessor, SignalProcessor


class InputCoordinator:
    """
    Sequential boundary between input threads and durable event persistence.

    Input threads emit signals into SignalChannel. Signal processors, such as
    MiningCoordinator, may derive durable domain events from those signals.
    Only durable events are forwarded to EventChannel for the DB writer.
    """

    def __init__(
        self,
        *,
        pending_signals: SignalChannel,
        pending_events: EventChannel,
        signal_processor: SignalProcessor | None = None,
    ) -> None:
        self.pending_signals = pending_signals
        self.pending_events = pending_events
        self.signal_processor = signal_processor or NoOpSignalProcessor()

    def run(self, *, stop_event: threading.Event) -> None:
        while not stop_event.is_set() or self.pending_signals.size() > 0:
            signal = self.pending_signals.take(timeout_s=0.1)
            if signal is None:
                continue

            derived_events = list(self.signal_processor.process(signal))

            for event in derived_events:
                self._route_durable_event(event)

    def _route_durable_event(self, event: EventBase) -> None:
        if should_persist_event(event):
            self.pending_events.emit(event)
