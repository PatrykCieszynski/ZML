from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from ctypes import windll
from pathlib import Path

import numpy as np

from zml_game_bridge.events.contracts import SignalSink
from zml_game_bridge.inputs.ocr.capture.window_capturer import WindowCapturer
from zml_game_bridge.inputs.ocr.config import OcrRoiProfile, load_ocr_roi_profile
from zml_game_bridge.inputs.ocr.pipelines.mining_finder.model import MiningFinderSignal
from zml_game_bridge.inputs.ocr.pipelines.mining_finder.pipeline import (
    MiningFinderPipeline,
    MiningFinderPipelineConfig,
)
from zml_game_bridge.inputs.ocr.pipelines.mining_finder.recording import (
    FinderCropRecorder,
    finder_recording_config_from_env,
)
from zml_game_bridge.inputs.ocr.pipelines.mining_finder.signals import (
    FinderHitHintSignal,
    FinderModeInvalidatedSignal,
    FinderModesChangedSignal,
    FinderNoResourcesSignal,
    FinderUnitsChangedSignal,
    ProbeFiredSignal,
)
from zml_game_bridge.inputs.ocr.pipelines.mining_finder.vision import VisionFinderFeatureDetector
from zml_game_bridge.inputs.ocr.pipelines.position.model import OcrPosition
from zml_game_bridge.inputs.ocr.pipelines.position.pipeline import PositionPipeline
from zml_game_bridge.inputs.ocr.profiling import (
    OcrProfiler,
    ocr_profiling_config_from_env,
)

PositionSink = Callable[[OcrPosition], None]
logger = logging.getLogger(__name__)


def start_ocr_input(
    *,
    position_sink: PositionSink,
    signal_sink: SignalSink | None = None,
    stop_event: threading.Event,
    target_hz: float = 10.0,
    finder_debug_logging: bool | None = None,
    finder_recording_modes: str | None = None,
    finder_recording_dir: Path | None = None,
    finder_recording_interval_s: float | None = None,
    finder_recording_low_confidence_interval_s: float | None = None,
    ocr_profiling_enabled: bool | None = None,
    ocr_profiling_interval_s: float | None = None,
    roi_profile_path: Path | None = None,
    roi_profile: OcrRoiProfile | None = None,
) -> None:
    windll.user32.SetProcessDPIAware()  # do once per process
    logger.info("ocr_worker_started target_hz=%s", target_hz)
    roi_profile = roi_profile or load_ocr_roi_profile(roi_profile_path)
    logger.info(
        "ocr_roi_profile_loaded name=%s finder_roi=%s compass_roi=%s deeds_roi=%s loot_roi=%s",
        roi_profile.name,
        roi_profile.screen_rois.finder.name,
        roi_profile.screen_rois.compass.name,
        roi_profile.screen_rois.deeds.name,
        roi_profile.screen_rois.loot.name if roi_profile.screen_rois.loot is not None else None,
    )
    cap = WindowCapturer(title_contains="Entropia Universe Client")
    period = 1.0 / target_hz
    next_t = time.perf_counter()

    ocr_profiling_config = ocr_profiling_config_from_env(
        enabled=ocr_profiling_enabled,
        interval_s=ocr_profiling_interval_s,
    )
    profiler = OcrProfiler(config=ocr_profiling_config)
    if profiler.enabled:
        logger.info("ocr_profiling_enabled interval_s=%s", ocr_profiling_config.interval_s)

    position_pipeline = PositionPipeline(
        roi_profile.position_rois.to_position_rois(),
        profiler=profiler,
    )
    if finder_debug_logging is None:
        finder_debug_logging = _env_bool("ZML_FINDER_DEBUG", default=False)
    if finder_debug_logging:
        _configure_finder_debug_logging()
        logger.info("finder_debug_enabled")

    finder_recording_config = finder_recording_config_from_env(
        modes=finder_recording_modes,
        root_dir=finder_recording_dir,
        interval_s=finder_recording_interval_s,
        low_confidence_interval_s=finder_recording_low_confidence_interval_s,
    )
    finder_recorder = (
        FinderCropRecorder(
            config=finder_recording_config,
            roi_name=roi_profile.screen_rois.finder.name,
        )
        if finder_recording_config.enabled
        else None
    )
    if finder_recorder is not None:
        logger.info(
            "finder_recording_enabled modes=%s dir=%s interval_ms=%s low_confidence_interval_ms=%s",
            ",".join(sorted(finder_recording_config.modes)),
            finder_recording_config.root_dir,
            finder_recording_config.interval_ms,
            finder_recording_config.low_confidence_min_interval_ms,
        )

    finder_pipeline = MiningFinderPipeline(
        detector=VisionFinderFeatureDetector(
            layout=roi_profile.finder_panel.to_panel_layout(),
            profiler=profiler,
        ),
        cfg=MiningFinderPipelineConfig(debug_logging=finder_debug_logging),
        frame_observer=finder_recorder,
    )
    # deeds_pipeline = ...     # step(deeds_roi, ts_ms) -> ...

    # optional: run slower pipelines less often
    finder_every_n = 5  # 10Hz/5 = 2Hz
    deeds_every_n = 10  # 1Hz
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

            capture_started_at = time.perf_counter()
            frame = cap.grab()
            profiler.record_elapsed("capture", capture_started_at)

            ts_ms = time.time_ns() // 1_000_000

            with profiler.measure("position.screen_crop"):
                compass = roi_profile.screen_rois.compass.crop(frame)
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
                        emit_started_at = time.perf_counter()
                        try:
                            emit_ts_ms = time.time_ns() // 1_000_000
                            for signal in signals:
                                latency_ms = max(0, emit_ts_ms - signal.ts_ms)
                                profiler.record("finder.signal_latency", float(latency_ms))
                                profiler.record(
                                    f"finder.signal_latency.{signal.kind}",
                                    float(latency_ms),
                                )
                                signal_sink(
                                    _to_finder_signal(
                                        signal,
                                        finder_position,
                                        roi_name=roi_profile.screen_rois.finder.name,
                                    )
                                )
                        finally:
                            profiler.record_elapsed("emit.signal", emit_started_at)
                finally:
                    finder_future = None
                    finder_position = None

            if tick % finder_every_n == 0 and finder_future is None:
                with profiler.measure("finder.screen_crop"):
                    finder = roi_profile.screen_rois.finder.crop(frame)
                if finder is not None:
                    finder_position = latest_position
                    finder_future = finder_executor.submit(
                        _run_finder_step,
                        finder_pipeline,
                        finder,
                        ts_ms,
                        profiler,
                        time.perf_counter(),
                    )

            if tick % deeds_every_n == 0:
                pass
                # deeds = roi_profile.screen_rois.deeds.crop(frame)
                # if deeds is not None:
                #     deeds_pipeline.step(deeds, ts_ms)
            profiler.maybe_log()
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
    logging.getLogger("zml_game_bridge.inputs.ocr.pipelines.mining_finder").setLevel(logging.DEBUG)


def _run_finder_step(
    pipeline: MiningFinderPipeline,
    finder_roi: np.ndarray,
    ts_ms: int,
    profiler: OcrProfiler,
    submitted_at: float,
) -> list[MiningFinderSignal]:
    profiler.record_elapsed("finder.queue_wait", submitted_at)
    step_started_at = time.perf_counter()
    try:
        return pipeline.step(finder_roi, ts_ms)
    finally:
        profiler.record_elapsed("finder.step", step_started_at)


def _to_finder_signal(
    signal: MiningFinderSignal,
    latest_position: OcrPosition | None,
    *,
    roi_name: str,
):
    match signal.kind:
        case "probe_fired":
            return ProbeFiredSignal(
                ts_ms=signal.ts_ms,
                position=latest_position.position if latest_position is not None else None,
                modes_mask=signal.modes_mask,
                probes_per_drop=signal.probes_per_drop,
                ammo_per_drop=signal.ammo_per_drop,
                raw_status_text=signal.raw_text,
                roi_name=roi_name,
                debug=signal.debug,
            )
        case "finder_modes_changed":
            if signal.modes_mask is None:
                raise RuntimeError("finder_modes_changed requires modes_mask")
            return FinderModesChangedSignal(
                ts_ms=signal.ts_ms,
                modes_mask=signal.modes_mask,
                previous_modes_mask=signal.previous_modes_mask,
                roi_name=roi_name,
                debug=signal.debug,
            )
        case "finder_mode_invalidated":
            return FinderModeInvalidatedSignal(
                ts_ms=signal.ts_ms,
                previous_modes_mask=signal.previous_modes_mask,
                roi_name=roi_name,
                debug=signal.debug,
            )
        case "finder_units_changed":
            return FinderUnitsChangedSignal(
                ts_ms=signal.ts_ms,
                probes_per_drop=signal.probes_per_drop,
                ammo_per_drop=signal.ammo_per_drop,
                raw_text=signal.raw_text,
                roi_name=roi_name,
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
                roi_name=roi_name,
            )
        case "finder_no_resources":
            return FinderNoResourcesSignal(
                ts_ms=signal.ts_ms,
                raw_status_text=signal.raw_text,
                roi_name=roi_name,
            )
