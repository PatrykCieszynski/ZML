from __future__ import annotations

from threading import Event
from typing import Protocol


class OcrInputSource(Protocol):
    """Runtime boundary for an OCR observation source."""

    def start(self, *, stop_event: Event) -> None:
        """Start producing OCR positions and finder signals."""
        ...

    def stop(self) -> None:
        """Wait for the OCR source to stop after the runtime stop signal is set."""
        ...
