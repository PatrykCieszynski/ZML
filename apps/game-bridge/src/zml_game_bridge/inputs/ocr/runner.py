from __future__ import annotations

import time
import threading
from collections.abc import Callable
from ctypes import windll

from zml_game_bridge.inputs.ocr.capture.window_capturer import WindowCapturer
from zml_game_bridge.inputs.ocr.capture.model import RoiRect
from zml_game_bridge.inputs.ocr.pipelines.position.model import OcrPosition, PositionRois
from zml_game_bridge.inputs.ocr.pipelines.position.pipeline import PositionPipeline

PositionSink = Callable[[OcrPosition], None]

# MVP hardcode
ROI_COMPASS = RoiRect(x1=2185, y1=965, x2=2551, y2=1411)
ROI_FINDER  = RoiRect(x1=20,   y1=20,  x2=700,  y2=250)
ROI_DEEDS   = RoiRect(x1=20,   y1=260, x2=700,  y2=520)


def start_ocr_input(
    *,
    position_sink: PositionSink,
    stop_event: threading.Event,
    target_hz: float = 10.0,
) -> None:
    windll.user32.SetProcessDPIAware()  # do once per process
    cap = WindowCapturer(title_contains="Entropia Universe Client")
    period = 1.0 / target_hz
    next_t = time.perf_counter()

    lat_lon_rois = PositionRois(
        planet=RoiRect(x1=23, x2=362, y1=0, y2=30),
        lon=RoiRect(x1=85, x2=145, y1=350, y2=370),
        lat=RoiRect(x1=90, x2=145, y1=375, y2=395),
    )

    # pipelines (MVP stubs)
    position_pipeline = PositionPipeline(lat_lon_rois)
    # finder_pipeline = ...    # step(finder_roi, ts_ms) -> ...
    # deeds_pipeline = ...     # step(deeds_roi, ts_ms) -> ...

    # optional: run slower pipelines less often
    finder_every_n = 5   # 10Hz/5 = 2Hz
    deeds_every_n = 10   # 1Hz
    tick = 0

    try:
        while not stop_event.is_set():
            now = time.perf_counter()
            sleep_s = next_t - now
            if sleep_s > 0:
                stop_event.wait(sleep_s)
            else:
                # We're behind schedule: drop backlog and resync.
                next_t = now
            next_t += period
            tick += 1


            frame = cap.grab()

            ts_ms = time.time_ns() // 1_000_000

            compass = ROI_COMPASS.crop(frame)
            if compass is not None:
                pos = position_pipeline.step(compass, ts_ms)
                if pos is not None:
                    position_sink(pos)

            if tick % finder_every_n == 0:
                pass
                # finder = ROI_FINDER.crop(frame)
                # if finder is not None:
                #     finder_pipeline.step(finder, ts_ms)

            if tick % deeds_every_n == 0:
                pass
                # deeds = ROI_DEEDS.crop(frame)
                # if deeds is not None:
                #     deeds_pipeline.step(deeds, ts_ms)
    finally:
        cap.close()
        position_pipeline.close()