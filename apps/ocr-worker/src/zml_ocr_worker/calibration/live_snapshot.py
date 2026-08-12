from __future__ import annotations

import json
import os
import time
from pathlib import Path

from zml_ocr_worker.calibration.finder import FinderLocator
from zml_ocr_worker.calibration.runtime import CompassCalibrationRuntime
from zml_ocr_worker.calibration.ui_diagnostics import (
    CalibrationUiDiagnosticsConfig,
    CalibrationUiDiagnosticsRecorder,
)
from zml_ocr_worker.capture.window_capturer import WindowCapturer
from zml_ocr_worker.config import load_ocr_roi_profile
from zml_ocr_worker.pipelines.mining_finder.presence import FinderPresenceDetector
from zml_ocr_worker.pipelines.position.pipeline import PositionPipeline


def run_live_calibration_snapshot(
    *,
    output_dir: Path,
    profile_path: Path | None,
) -> int:
    _set_process_dpi_aware()
    profile = load_ocr_roi_profile(profile_path)
    recorder = CalibrationUiDiagnosticsRecorder(
        config=CalibrationUiDiagnosticsConfig(
            root_dir=output_dir,
            interval_ms=0,
            context_padding_px=32,
        )
    )
    recorder.clear()

    capturer = WindowCapturer(title_contains="Entropia Universe Client")
    position_pipeline = PositionPipeline(profile.position_rois.to_position_rois())
    compass_runtime = CompassCalibrationRuntime(position_pipeline=position_pipeline)
    finder_locator = FinderLocator(presence_detector=FinderPresenceDetector())
    ts_ms = time.time_ns() // 1_000_000

    result: dict[str, object] = {
        "capturedTsMs": ts_ms,
        "finder": {"available": False},
        "compass": {"available": False},
    }
    try:
        frame = capturer.grab()

        finder = finder_locator.locate(frame)
        if finder is not None:
            recorder.record_finder(
                frame,
                finder=finder,
                layout=profile.finder_panel.to_panel_layout(),
                ts_ms=ts_ms,
            )
            result["finder"] = {"available": True}

        calibrated = compass_runtime.step(frame, ts_ms=ts_ms)
        if calibrated.compass is not None:
            recorder.record_compass(
                frame,
                compass=calibrated.compass,
                rois=compass_runtime.active_rois,
                ts_ms=ts_ms,
            )
            result["compass"] = {"available": True}
    finally:
        capturer.close()
        compass_runtime.close()
        position_pipeline.close()

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "snapshot.json").write_text(
        json.dumps(result, ensure_ascii=False),
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


def _set_process_dpi_aware() -> None:
    if os.name != "nt":
        return
    try:
        from ctypes import windll

        windll.user32.SetProcessDPIAware()
    except Exception:
        pass
