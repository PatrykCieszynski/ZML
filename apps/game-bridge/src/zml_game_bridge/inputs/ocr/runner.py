from __future__ import annotations

import threading
from collections.abc import Callable

from zml_game_bridge.inputs.ocr.model import OcrPosition
from zml_game_bridge.inputs.ocr.pipelines.position import run_position_stub

PositionSink = Callable[[OcrPosition], None]


def start_ocr_input(*, position_sink: PositionSink, stop_event: threading.Event) -> None:
    # MVP: only position stub. Later: shared screen capture + pipelines.
    run_position_stub(position_sink=position_sink, stop_event=stop_event)
