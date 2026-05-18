from __future__ import annotations

from threading import Lock

from zml_game_bridge.inputs.ocr.pipelines.position.model import OcrPosition


class LatestPositionState:
    """
    Volatile latest-position cache.

    Position updates are high-frequency and are not part of the durable event
    store. The cache gives future read-model projectors a thread-safe snapshot
    without turning every OCR tick into a database write.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._position: OcrPosition | None = None

    def update(self, position: OcrPosition) -> None:
        with self._lock:
            self._position = position

    def get(self) -> OcrPosition | None:
        with self._lock:
            return self._position
