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
from zml_ocr_protocol.messages import AgentToBridgeMessage

from zml_ocr_worker.calibration.finder import FinderLocator
from zml_ocr_worker.calibration.model import LocatedRegion
from zml_ocr_worker.calibration.persistence import CompassCalibrationStore
from zml_ocr_worker.calibration.recording import (
    CalibrationSnapshotRecorder,
    calibration_snapshot_config_from_env,
)
from zml_ocr_worker.calibration.runtime import CompassCalibrationRuntime
from zml_ocr_worker.capture.window_capturer import (
    WindowCapturer,
    WindowCaptureUnavailableError,
)
from zml_ocr_worker.config import OcrRoiProfile, load_ocr_roi_profile
from zml_ocr_worker.pipelines.mining_finder.model import MiningFinderSignal
from zml_ocr_worker.pipelines.mining_finder.pipeline import (
    MiningFinderPipeline,
    MiningFinderPipelineConfig,
)
from zml_ocr_worker.pipelines.mining_finder.presence import FinderPresenceDetector
from zml_ocr_worker.pipelines.mining_finder.recording import (
    FinderCropRecorder,
    finder_recording_config_from_env,
)
from zml_ocr_worker.pipelines.mining_finder.vision import VisionFinderFeatureDetector
from zml_ocr_worker.pipelines.position.pipeline import PositionPipeline
from zml_ocr_worker.runtime.message_factory import AgentMessageFactory
from zml_ocr_worker.runtime.profiling import (
    OcrProfiler,
    ocr_profiling_config_from_env,
)

MessageSink = Callable[[AgentToBridgeMessage], None]
logger = logging.getLogger(__name__)

_TARGET_WINDOW_RETRY_INTERVAL_S = 1.0
_FINDER_REACQUIRE_INTERVAL_S = 2.0


def start_ocr_input(
    *,
    message_sink: MessageSink,
    stop_event: threading.Event,
    message_factory: AgentMessageFactory | None = None,
    target_hz: float = 10.0,
    finder_debug_logging: bool | None = None,
    finder_recording_modes: str | None = None,
    finder_recording_dir: Path | None = None,
    finder_recording_interval_s: float | None = None,
    finder_recording_max_samples: int | None = None,
    finder_presence_check_enabled: bool | None = None,
    ocr_profiling_enabled: bool | None = None,
    ocr_profiling_interval_s: float | None = None,
    roi_profile_path: Path | None = None,
    roi_profile: OcrRoiProfile | None = None,
) -> None:
    message_factory = message_factory or AgentMessageFactory()
    windll.user32.SetProcessDPIAware()  # do once per process
    logger.info("ocr_worker_started target_hz=%s calibration=auto", target_hz)
    roi_profile = roi_profile or load_ocr_roi_profile(roi_profile_path)
    logger.info(
        "ocr_roi_profile_loaded name=%s deeds_roi=%s loot_roi=%s",
        roi_profile.name,
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

    position_rois = roi_profile.position_rois.to_position_rois()
    position_pipeline = PositionPipeline(
        position_rois,
        profiler=profiler,
    )
    compass_calibration_store = CompassCalibrationStore()
    logger.info(
        "compass_calibration_persistence_enabled path=%s",
        compass_calibration_store.path,
    )
    compass_calibration = CompassCalibrationRuntime(
        position_pipeline=position_pipeline,
        state_store=compass_calibration_store,
    )
    last_compass_rect: tuple[int, int, int, int] | None = None

    calibration_snapshot_config = calibration_snapshot_config_from_env()
    calibration_snapshot_recorder = CalibrationSnapshotRecorder(
        config=calibration_snapshot_config,
    )
    if calibration_snapshot_config.enabled:
        logger.info(
            "ocr_suspect_capture_enabled dir=%s interval_ms=%s max_samples=%s",
            calibration_snapshot_config.root_dir,
            calibration_snapshot_config.interval_ms,
            calibration_snapshot_config.max_samples,
        )

    if finder_debug_logging is None:
        finder_debug_logging = _env_bool("ZML_FINDER_DEBUG", default=False)
    if finder_debug_logging:
        _configure_finder_debug_logging()
        logger.info("finder_debug_enabled")
    if finder_presence_check_enabled is None:
        finder_presence_check_enabled = _env_bool("ZML_FINDER_PRESENCE_CHECK", default=True)
    finder_presence_detector = FinderPresenceDetector()
    finder_locator = FinderLocator(presence_detector=finder_presence_detector)
    located_finder: LocatedRegion | None = None
    next_finder_search_at = 0.0
    last_finder_present: bool | None = None
    logger.info("finder_presence_check_enabled enabled=%s", finder_presence_check_enabled)

    finder_recording_config = finder_recording_config_from_env(
        modes=finder_recording_modes,
        root_dir=finder_recording_dir,
        interval_s=finder_recording_interval_s,
        max_samples=finder_recording_max_samples,
    )
    finder_recorder = (
        FinderCropRecorder(
            config=finder_recording_config,
            roi_name="finder_auto",
        )
        if finder_recording_config.enabled
        else None
    )
    if finder_recorder is not None:
        logger.info(
            "finder_recording_enabled modes=%s dir=%s interval_ms=%s max_samples=%s",
            ",".join(sorted(finder_recording_config.modes)),
            finder_recording_config.root_dir,
            finder_recording_config.interval_ms,
            finder_recording_config.max_samples,
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
    finder_future: Future[list[MiningFinderSignal]] | None = None
    finder_locator_future: Future[LocatedRegion | None] | None = None
    finder_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="zml-finder-ocr")
    finder_locator_executor = ThreadPoolExecutor(
        max_workers=1,
        thread_name_prefix="zml-finder-locator",
    )
    target_window_available: bool | None = None

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
            frame, capture_error = _try_grab_frame(cap)
            profiler.record_elapsed("capture", capture_started_at)
            if frame is None:
                if target_window_available is not False:
                    logger.info("ocr_target_window_waiting error=%s", capture_error)
                    message_sink(
                        message_factory.status(
                            state="waiting_for_window",
                            capture_available=False,
                            code="window_unavailable",
                            detail=capture_error,
                        )
                    )
                target_window_available = False
                stop_event.wait(_TARGET_WINDOW_RETRY_INTERVAL_S)
                next_t = time.perf_counter()
                continue
            if target_window_available is not True:
                logger.info("ocr_target_window_available")
                message_sink(
                    message_factory.status(
                        state="running",
                        capture_available=True,
                    )
                )
            target_window_available = True

            ts_ms = time.time_ns() // 1_000_000

            with profiler.measure("position.auto_calibration"):
                calibrated_step = compass_calibration.step(frame, ts_ms=ts_ms)
            compass = calibrated_step.compass_roi
            located_compass = calibrated_step.compass
            if located_compass is not None:
                rect = located_compass.rect
                rect_key = (rect.x1, rect.y1, rect.x2, rect.y2)
                if rect_key != last_compass_rect:
                    logger.info(
                        "compass_auto_calibrated rect=%s confidence=%.3f scale=%.3f layout=%s",
                        rect_key,
                        located_compass.confidence,
                        located_compass.scale,
                        compass_calibration.layout_index,
                    )
                    last_compass_rect = rect_key
            if calibrated_step.reacquire_requested:
                logger.info("compass_auto_reacquire_requested")
                last_compass_rect = None

            if compass is not None and located_compass is not None:
                active_rois = compass_calibration.active_rois
                if active_rois is not None:
                    try:
                        sample_dir = calibration_snapshot_recorder.record(
                            compass,
                            compass=located_compass,
                            rois=active_rois,
                            read=calibrated_step.read,
                            layout_index=compass_calibration.layout_index,
                            ts_ms=ts_ms,
                        )
                        if sample_dir is not None:
                            logger.info(
                                "ocr_suspect_capture_recorded dir=%s",
                                sample_dir,
                            )
                    except Exception:
                        logger.warning(
                            "ocr_suspect_capture_failed ts_ms=%s",
                            ts_ms,
                            exc_info=True,
                        )

                pos = calibrated_step.read.position
                if pos is not None:
                    message_sink(
                        message_factory.position(
                            pos,
                            roi_name="compass_auto",
                        )
                    )

            if finder_future is not None and finder_future.done():
                try:
                    signals = finder_future.result()
                except Exception:
                    logger.exception("finder_ocr_worker_crashed")
                else:
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
                            message_sink(
                                message_factory.finder(
                                    signal,
                                    roi_name="finder_auto",
                                )
                            )
                    finally:
                        profiler.record_elapsed("emit.signal", emit_started_at)
                finally:
                    finder_future = None

            if finder_locator_future is not None and finder_locator_future.done():
                try:
                    located_finder = finder_locator_future.result()
                except Exception:
                    logger.exception("finder_locator_worker_crashed")
                    located_finder = None
                else:
                    if located_finder is not None:
                        rect = located_finder.rect
                        logger.info(
                            "finder_auto_calibrated rect=%s confidence=%.3f scale=%.3f",
                            (rect.x1, rect.y1, rect.x2, rect.y2),
                            located_finder.confidence,
                            located_finder.scale,
                        )
                finally:
                    finder_locator_future = None
                    next_finder_search_at = time.perf_counter() + _FINDER_REACQUIRE_INTERVAL_S

            if tick % finder_every_n == 0 and finder_future is None:
                finder: np.ndarray | None = None
                if located_finder is not None:
                    finder = located_finder.rect.crop(frame)
                if (
                    finder is None
                    and finder_locator_future is None
                    and time.perf_counter() >= next_finder_search_at
                ):
                    # Full-frame Finder discovery is much more expensive than the
                    # locked presence guard. Run it off the capture thread so an
                    # absent/moved Finder cannot stall position OCR for seconds.
                    finder_locator_future = finder_locator_executor.submit(
                        finder_locator.locate,
                        frame,
                    )

                if finder is not None:
                    should_run_finder = True
                    if finder_presence_check_enabled:
                        with profiler.measure("finder.presence"):
                            presence = finder_presence_detector.detect(finder)
                        if finder_debug_logging and presence.present != last_finder_present:
                            logger.debug(
                                "finder_presence_changed present=%s score=%.3f "
                                "panel_dark=%.3f grid=%.3f blue=%.3f green=%.3f",
                                presence.present,
                                presence.score,
                                presence.panel_dark_score,
                                presence.grid_score,
                                presence.blue_score,
                                presence.green_score,
                            )
                        last_finder_present = presence.present
                        if not presence.present:
                            should_run_finder = False
                            if located_finder is not None:
                                logger.info("finder_auto_reacquire_requested")
                                located_finder = None
                                next_finder_search_at = time.perf_counter() + 0.5
                    if should_run_finder:
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
        if finder_locator_future is not None:
            finder_locator_future.cancel()
        finder_executor.shutdown(wait=True, cancel_futures=True)
        finder_locator_executor.shutdown(wait=True, cancel_futures=True)
        cap.close()
        compass_calibration.close()
        position_pipeline.close()
        finder_pipeline.close()


def _try_grab_frame(
    capturer: WindowCapturer,
) -> tuple[np.ndarray | None, str | None]:
    try:
        return capturer.grab(), None
    except WindowCaptureUnavailableError as exc:
        capturer.close()
        return None, str(exc)


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
    logging.getLogger("zml_ocr_worker.pipelines.mining_finder").setLevel(logging.DEBUG)


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
