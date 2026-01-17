from __future__ import annotations

import asyncio

from zml_game_bridge.inputs.ocr.pipelines.position.model import OcrPosition


class OcrPositionHub:
    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._queues: set[asyncio.Queue[OcrPosition]] = set()
        self._last: OcrPosition | None = None

    def publish_threadsafe(self, pos: OcrPosition) -> None:
        """Called from non-async threads."""
        self._loop.call_soon_threadsafe(self._publish_on_loop, pos)

    def _publish_on_loop(self, pos: OcrPosition) -> None:
        self._last = pos
        for q in list(self._queues):
            # "Latest only": keep queue size at 1.
            while q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    break
            try:
                q.put_nowait(pos)
            except asyncio.QueueFull:
                # Shouldn't happen due to full() draining, but keep safe.
                pass

    def subscribe(self) -> tuple[asyncio.Queue[OcrPosition], OcrPosition | None]:
        q: asyncio.Queue[OcrPosition] = asyncio.Queue(maxsize=1)
        self._queues.add(q)
        return q, self._last

    def unsubscribe(self, q: asyncio.Queue[OcrPosition]) -> None:
        self._queues.discard(q)
