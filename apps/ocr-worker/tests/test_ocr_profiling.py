from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from zml_ocr_worker.runtime.profiling import (
    OcrProfiler,
    OcrProfilingConfig,
    ocr_profiling_config_from_env,
)


def test_ocr_profiler_logs_window_summary_and_persists_health(tmp_path: Path, caplog) -> None:
    health_path = tmp_path / "health.json"
    profiler = OcrProfiler(
        config=OcrProfilingConfig(
            enabled=True,
            interval_s=0.1,
            health_path=health_path,
        )
    )
    profiler.record("finder.ocr", 10.0)
    profiler.record("finder.ocr", 30.0)
    profiler.increment("finder.frames")
    profiler.increment("finder.frames")

    time.sleep(0.11)
    with caplog.at_level(logging.INFO):
        profiler.maybe_log()

    assert "ocr_health_summary" in caplog.text
    assert "scope=all" in caplog.text
    assert "finder.ocr_count=2" in caplog.text
    assert "finder.ocr_avg_ms=20.00" in caplog.text
    assert "finder.frames=2" in caplog.text

    payload = json.loads(health_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["counters"]["finder.frames"] == 2
    assert payload["lifetime_counters"]["finder.frames"] == 2
    assert payload["timings_ms"]["finder.ocr"]["count"] == 2
    assert payload["timings_ms"]["finder.ocr"]["avg_ms"] == 20.0


def test_ocr_profiler_logs_scoped_summaries(tmp_path: Path, caplog) -> None:
    profiler = OcrProfiler(
        config=OcrProfilingConfig(
            enabled=True,
            interval_s=0.1,
            health_path=tmp_path / "health.json",
        )
    )
    profiler.record("position.ocr", 5.0)
    profiler.record("finder.ocr", 15.0)
    profiler.record("capture", 2.0)
    profiler.increment("position.valid", 3)

    time.sleep(0.11)
    with caplog.at_level(logging.INFO):
        profiler.maybe_log()

    records_by_scope = {}
    for record in caplog.records:
        message = record.getMessage()
        if "ocr_health_summary scope=" not in message:
            continue
        scope = message.split("scope=", maxsplit=1)[1].split(" ", maxsplit=1)[0]
        records_by_scope[scope] = record
    assert set(records_by_scope) == {"all", "finder", "position"}
    assert records_by_scope["all"].name == "zml_ocr_worker.runtime.profiling"
    assert records_by_scope["finder"].name.endswith(".profiling.finder")
    assert records_by_scope["position"].name.endswith(".profiling.position")
    assert "capture_count=1" in records_by_scope["all"].getMessage()
    assert "capture_count=1" not in records_by_scope["finder"].getMessage()
    assert "finder.ocr_count=1" in records_by_scope["finder"].getMessage()
    assert "position.ocr_count=1" in records_by_scope["position"].getMessage()
    assert "position.valid=3" in records_by_scope["position"].getMessage()


def test_ocr_profiler_ignores_metrics_when_disabled(tmp_path: Path, caplog) -> None:
    health_path = tmp_path / "health.json"
    profiler = OcrProfiler(
        config=OcrProfilingConfig(
            enabled=False,
            interval_s=0.1,
            health_path=health_path,
        )
    )
    profiler.record("finder.ocr", 10.0)
    profiler.increment("finder.frames")

    time.sleep(0.11)
    with caplog.at_level(logging.INFO):
        profiler.maybe_log()

    assert "ocr_health_summary" not in caplog.text
    assert not health_path.exists()


def test_ocr_profiling_is_enabled_by_default_and_can_be_disabled(monkeypatch) -> None:
    monkeypatch.delenv("ZML_OCR_PROFILING", raising=False)
    assert ocr_profiling_config_from_env().enabled is True

    monkeypatch.setenv("ZML_OCR_PROFILING", "0")
    assert ocr_profiling_config_from_env().enabled is False

    monkeypatch.setenv("ZML_OCR_PROFILING", "1")
    monkeypatch.setenv("ZML_OCR_PROFILING_INTERVAL_S", "2.5")
    config = ocr_profiling_config_from_env()
    assert config.enabled is True
    assert config.interval_s == 2.5
