from __future__ import annotations

import asyncio
from contextlib import suppress

from zml_game_bridge.application.position.model import PositionSnapshot


class PositionHub:
    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._queues: set[asyncio.Queue[PositionSnapshot]] = set()
        self._last: PositionSnapshot | None = None

    def publish_threadsafe(self, pos: PositionSnapshot) -> None:
        """Called from non-async threads."""
        self._loop.call_soon_threadsafe(self._publish_on_loop, pos)

    def _publish_on_loop(self, pos: PositionSnapshot) -> None:
        self._last = pos
        for q in list(self._queues):
            # "Latest only": keep queue size at 1.
            while q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    break
            with suppress(asyncio.QueueFull):
                q.put_nowait(pos)

    def subscribe(self) -> tuple[asyncio.Queue[PositionSnapshot], PositionSnapshot | None]:
        q: asyncio.Queue[PositionSnapshot] = asyncio.Queue(maxsize=1)
        self._queues.add(q)
        return q, self._last

    def unsubscribe(self, q: asyncio.Queue[PositionSnapshot]) -> None:
        self._queues.discard(q)
