from threading import Lock

from zml_game_bridge.events.bus import PersistedEventBus, EventHandler, Subscription
from zml_game_bridge.events.envelope import EventEnvelope


class InMemoryPersistedEventBus(PersistedEventBus):
    def __init__(self) -> None:
        self._handlers: dict[int, EventHandler] = {}
        self._next_id: int = 0
        self._lock = Lock()

    def publish(self, envelope: EventEnvelope) -> None:
        handlers: list[EventHandler]
        with self._lock:
            handlers = list(self._handlers.values())
        for handler in handlers:
            try:
                handler(envelope)
            except Exception as e:
                #TODO log error properly
                print(f"Error in event handler: {e}")
                continue


    def subscribe(self, handler: EventHandler) -> Subscription:
        with self._lock:
            sub_id = self._next_id
            self._next_id += 1
            self._handlers[sub_id] = handler

        def unsubscribe() -> None:
            with self._lock:
                self._handlers.pop(sub_id, None)

        return Subscription(unsubscribe=unsubscribe)


    def close(self) -> None:
        with self._lock:
            self._handlers.clear()