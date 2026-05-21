from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from ctypes import windll

import numpy as np

from zml_game_bridge.events.contracts import SignalSink
from zml_game_bridge.inputs.ocr.capture.model import RoiRect
from zml_game_bridge.inputs.ocr.capture.window_capturer import WindowCapturer
from zml_game_bridge.inputs.ocr.pipelines.mining_finder.model import MiningFinderSignal
from zml_game_bridge.inputs.ocr.pipelines.mining_finder.pipeline import (
    MiningFinderPipeline,
    MiningFinderPipelineConfig,
)
from zml_game_bridge.inputs.ocr.pipelines.mining_finder.signals import (
    FinderHitHintSignal,
    FinderModeInvalidatedSignal,
    FinderModesChangedSignal,
    FinderNoResourcesSignal,
    FinderUnitsChangedSignal,
    ProbeFiredSignal,
)
from zml_game_bridge.inputs.ocr.pipelines.position.model import OcrPosition, PositionRois
from zml_game_bridge.inputs.ocr.pipelines.position.pipeline import PositionPipeline

PositionSink = Callable[[OcrPosition], None]
logger = logging.getLogger(__name__)

# MVP hardcode
ROI_COMPASS = RoiRect(x1=2185, y1=965, x2=2551, y2=1411)
ROI_DEEDS = RoiRect(x1=20, y1=260, x2=700, y2=520)


def start_ocr_input(
    *,
    position_sink: PositionSink,
    signal_sink: SignalSink | None = None,
    stop_event: threading.Event,
    target_hz: float = 10.0,
    finder_debug_logging: bool | None = None,
) -> None:
    windll.user32.SetProcessDPIAware()  # do once per process
    logger.info("ocr_worker_started target_hz=%s", target_hz)
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
    if finder_debug_logging is None:
        finder_debug_logging = _env_bool("ZML_FINDER_DEBUG", default=False)
    if finder_debug_logging:
        _configure_finder_debug_logging()
        logger.info("finder_debug_enabled")

    finder_pipeline = MiningFinderPipeline(
        cfg=MiningFinderPipelineConfig(debug_logging=finder_debug_logging)
    )
    # deeds_pipeline = ...     # step(deeds_roi, ts_ms) -> ...

    # optional: run slower pipelines less often
    finder_every_n = 5   # 10Hz/5 = 2Hz
    deeds_every_n = 10   # 1Hz
    tick = 0
    latest_position: OcrPosition | None = None
    finder_future: Future[list[MiningFinderSignal]] | None = None
    finder_position: OcrPosition | None = None
    finder_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="zml-finder-ocr")

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
                    latest_position = pos
                    position_sink(pos)

            if finder_future is not None and finder_future.done():
                try:
                    signals = finder_future.result()
                except Exception:
                    logger.exception("finder_ocr_worker_crashed")
                else:
                    if signal_sink is not None:
                        for signal in signals:
                            signal_sink(_to_finder_signal(signal, finder_position))
                finally:
                    finder_future = None
                    finder_position = None

            if tick % finder_every_n == 0 and finder_future is None:
                finder = _finder_mvp_roi(frame).crop(frame)
                if finder is not None:
                    finder_position = latest_position
                    finder_future = finder_executor.submit(finder_pipeline.step, finder, ts_ms)

            if tick % deeds_every_n == 0:
                pass
                # deeds = ROI_DEEDS.crop(frame)
                # if deeds is not None:
                #     deeds_pipeline.step(deeds, ts_ms)
    except Exception:
        logger.exception("ocr_worker_crashed")
        raise
    finally:
        if finder_future is not None:
            finder_future.cancel()
        finder_executor.shutdown(wait=True, cancel_futures=True)
        cap.close()
        position_pipeline.close()
        finder_pipeline.close()


def _finder_mvp_roi(frame: np.ndarray) -> RoiRect:
    height = int(frame.shape[0])
    width = int(frame.shape[1])
    margin = 3
    roi_width = 347
    roi_height = 239
    return RoiRect(
        x1=margin,
        x2=min(width, margin + roi_width),
        y1=max(0, height - margin - roi_height),
        y2=max(0, height - margin),
    )


def _env_bool(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _configure_finder_debug_logging() -> None:
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    logger.setLevel(logging.DEBUG)
    logging.getLogger("zml_game_bridge.inputs.ocr.pipelines.mining_finder").setLevel(
        logging.DEBUG
    )


def _to_finder_signal(signal: MiningFinderSignal, latest_position: OcrPosition | None):
    match signal.kind:
        case "probe_fired":
            return ProbeFiredSignal(
                ts_ms=signal.ts_ms,
                position=latest_position.position if latest_position is not None else None,
                modes_mask=signal.modes_mask,
                probes_per_drop=signal.probes_per_drop,
                ammo_per_drop=signal.ammo_per_drop,
                raw_status_text=signal.raw_text,
                debug=signal.debug,
            )
        case "finder_modes_changed":
            if signal.modes_mask is None:
                raise RuntimeError("finder_modes_changed requires modes_mask")
            return FinderModesChangedSignal(
                ts_ms=signal.ts_ms,
                modes_mask=signal.modes_mask,
                previous_modes_mask=signal.previous_modes_mask,
                debug=signal.debug,
            )
        case "finder_mode_invalidated":
            return FinderModeInvalidatedSignal(
                ts_ms=signal.ts_ms,
                previous_modes_mask=signal.previous_modes_mask,
                debug=signal.debug,
            )
        case "finder_units_changed":
            return FinderUnitsChangedSignal(
                ts_ms=signal.ts_ms,
                probes_per_drop=signal.probes_per_drop,
                ammo_per_drop=signal.ammo_per_drop,
                raw_text=signal.raw_text,
            )
        case "finder_hit_hint":
            if (
                signal.hit_size_label is None
                or signal.hit_size_index is None
                or signal.resource_name is None
            ):
                raise RuntimeError("finder_hit_hint requires size label, index, and resource")
            return FinderHitHintSignal(
                ts_ms=signal.ts_ms,
                size_label=signal.hit_size_label,
                size_index=signal.hit_size_index,
                resource_name=signal.resource_name,
                range_m=signal.range_m,
                depth_m=signal.depth_m,
                raw_status_text=signal.raw_text,
                raw_details_text=signal.raw_details_text,
            )
        case "finder_no_resources":
            return FinderNoResourcesSignal(
                ts_ms=signal.ts_ms,
                raw_status_text=signal.raw_text,
            )
