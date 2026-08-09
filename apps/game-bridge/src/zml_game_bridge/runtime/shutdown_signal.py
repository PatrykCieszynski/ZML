from __future__ import annotations

import asyncio
import signal
import sys
import threading
from types import FrameType


class RuntimeShutdownSignal:
    """Process-wide shutdown notification for long-lived API streams."""

    def __init__(self) -> None:
        self._requested = threading.Event()

    def request(self) -> None:
        self._requested.set()

    def reset(self) -> None:
        self._requested.clear()

    def is_requested(self) -> bool:
        return self._requested.is_set()

    async def wait(self) -> None:
        while not self._requested.is_set():
            await asyncio.sleep(0.05)

    def install_signal_forwarders(self) -> None:
        if threading.current_thread() is not threading.main_thread():
            return

        handled_signals = [signal.SIGINT, signal.SIGTERM]
        if sys.platform == "win32":
            handled_signals.append(signal.SIGBREAK)

        for signal_number in handled_signals:
            previous_handler = signal.getsignal(signal_number)
            if not callable(previous_handler):
                continue

            def forward_signal(
                received_signal: int,
                frame: FrameType | None,
                previous_handler=previous_handler,
            ) -> None:
                self.request()
                previous_handler(received_signal, frame)

            signal.signal(signal_number, forward_signal)


process_shutdown_signal = RuntimeShutdownSignal()
