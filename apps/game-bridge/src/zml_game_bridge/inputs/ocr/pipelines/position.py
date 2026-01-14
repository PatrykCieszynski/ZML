from __future__ import annotations

import threading
import time
from collections.abc import Callable

from zml_game_bridge.common.models import WorldPos
from zml_game_bridge.inputs.ocr.model import OcrPosition

PositionSink = Callable[[OcrPosition], None]


def run_position_stub(*, position_sink: PositionSink, stop_event: threading.Event, interval_s: float = 0.2) -> None:
    x, y, z = 100000, 200000, 120
    planet = "Calypso"

    while not stop_event.is_set():
        ts_ms = time.time_ns() // 1_000_000
        sample = OcrPosition(ts_ms=ts_ms, position=WorldPos(planet_name=planet, x=x, y=y, z=z))
        position_sink(sample)

        x += 1
        y += 1
        time.sleep(interval_s)
