from __future__ import annotations

import logging
import time

from zml_game_bridge.inputs.ocr.profiling import (
    OcrProfiler,
    OcrProfilingConfig,
    ocr_profiling_config_from_env,
)


def test_ocr_profiler_logs_window_summary(caplog) -> None:
    profiler = OcrProfiler(config=OcrProfilingConfig(enabled=True, interval_s=0.1))
    profiler.record("finder.ocr", 10.0)
    profiler.record("finder.ocr", 30.0)

    time.sleep(0.11)
    with caplog.at_level(logging.INFO):
        profiler.maybe_log()

    assert "ocr_profile_summary" in caplog.text
    assert "finder.ocr_count=2" in caplog.text
    assert "finder.ocr_avg_ms=20.00" in caplog.text


def test_ocr_profiler_ignores_metrics_when_disabled(caplog) -> None:
    profiler = OcrProfiler(config=OcrProfilingConfig(enabled=False, interval_s=0.1))
    profiler.record("finder.ocr", 10.0)

    time.sleep(0.11)
    with caplog.at_level(logging.INFO):
        profiler.maybe_log()

    assert "ocr_profile_summary" not in caplog.text


def test_ocr_profiling_config_from_env(monkeypatch) -> None:
    monkeypatch.setenv("ZML_OCR_PROFILING", "1")
    monkeypatch.setenv("ZML_OCR_PROFILING_INTERVAL_S", "2.5")

    config = ocr_profiling_config_from_env()

    assert config.enabled is True
    assert config.interval_s == 2.5
