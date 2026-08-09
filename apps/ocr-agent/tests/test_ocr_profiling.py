from __future__ import annotations

import logging
import time

from zml_ocr_agent.profiling import (
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
    assert "scope=all" in caplog.text
    assert "finder.ocr_count=2" in caplog.text
    assert "finder.ocr_avg_ms=20.00" in caplog.text


def test_ocr_profiler_logs_scoped_summaries(caplog) -> None:
    profiler = OcrProfiler(config=OcrProfilingConfig(enabled=True, interval_s=0.1))
    profiler.record("position.ocr", 5.0)
    profiler.record("finder.ocr", 15.0)
    profiler.record("capture", 2.0)

    time.sleep(0.11)
    with caplog.at_level(logging.INFO):
        profiler.maybe_log()

    records_by_scope = {}
    for record in caplog.records:
        message = record.getMessage()
        if "ocr_profile_summary scope=" not in message:
            continue
        scope = message.split("scope=", maxsplit=1)[1].split(" ", maxsplit=1)[0]
        records_by_scope[scope] = record
    assert set(records_by_scope) == {"all", "finder", "position"}
    assert records_by_scope["all"].name == "zml_ocr_agent.profiling"
    assert records_by_scope["finder"].name.endswith(".profiling.finder")
    assert records_by_scope["position"].name.endswith(".profiling.position")
    assert "capture_count=1" in records_by_scope["all"].getMessage()
    assert "capture_count=1" not in records_by_scope["finder"].getMessage()
    assert "finder.ocr_count=1" in records_by_scope["finder"].getMessage()
    assert "position.ocr_count=1" in records_by_scope["position"].getMessage()


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
