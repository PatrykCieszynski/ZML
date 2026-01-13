from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from typing import Dict

from zml_game_bridge.events.envelope import EventEnvelope


@dataclass(frozen=True, slots=True)
class SseClient:
    client_id: int
    queue: asyncio.Queue[EventEnvelope]


class SseHub:
    """
    Thread -> asyncio bridge.

    - on_envelope() can be called from ANY thread (e.g., DbWriter thread)
    - each SSE connection registers its own asyncio.Queue
    - broadcasting is scheduled onto the event loop thread
    """

    def __init__(self, loop: asyncio.AbstractEventLoop, *, queue_maxsize: int = 200) -> None:
        self._loop = loop
        self._queue_maxsize = queue_maxsize

        self._lock = threading.Lock()
        self._next_id = 1
        self._clients: Dict[int, asyncio.Queue[EventEnvelope]] = {}

    def register(self) -> SseClient:
        """
        Called from the event-loop thread (FastAPI request handler).
        """
        q: asyncio.Queue[EventEnvelope] = asyncio.Queue(maxsize=self._queue_maxsize)
        with self._lock:
            client_id = self._next_id
            self._next_id += 1
            self._clients[client_id] = q
        return SseClient(client_id=client_id, queue=q)

    def unregister(self, client_id: int) -> None:
        with self._lock:
            self._clients.pop(client_id, None)

    def on_envelope(self, env: EventEnvelope) -> None:
        """
        Called from DbWriter thread (or any thread).
        Must not block.
        """
        try:
            self._loop.call_soon_threadsafe(self._broadcast, env)
        except RuntimeError:
            # loop is closed (shutdown/reload) -> ignore
            return

    def _broadcast(self, env: EventEnvelope) -> None:
        """
        Runs on event-loop thread.
        """
        with self._lock:
            queues = list(self._clients.values())

        for q in queues:
            # Backpressure policy for slow clients:
            # keep the stream "near-real-time" by dropping oldest.
            if q.full():
                try:
                    _ = q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                q.put_nowait(env)
            except asyncio.QueueFull:
                # if still full -> drop newest
                continue
