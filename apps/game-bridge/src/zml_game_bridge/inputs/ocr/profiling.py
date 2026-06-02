from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass

logger = logging.getLogger(__name__)
_SCOPED_LOGGERS = {
    "position": logging.getLogger(f"{__name__}.position"),
    "finder": logging.getLogger(f"{__name__}.finder"),
    "deed": logging.getLogger(f"{__name__}.deed"),
}


@dataclass(frozen=True, slots=True)
class OcrProfilingConfig:
    enabled: bool = False
    interval_s: float = 10.0


class OcrProfiler:
    def __init__(self, *, config: OcrProfilingConfig) -> None:
        self._config = config
        self._lock = threading.Lock()
        self._window_started_at = time.perf_counter()
        self._metrics: dict[str, list[float]] = {}

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    @contextmanager
    def measure(self, name: str) -> Generator[None]:
        if not self.enabled:
            yield
            return

        started_at = time.perf_counter()
        try:
            yield
        finally:
            self.record_elapsed(name, started_at)

    def record_elapsed(self, name: str, started_at: float) -> None:
        if not self.enabled:
            return
        self.record(name, (time.perf_counter() - started_at) * 1000.0)

    def record(self, name: str, value: float) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._metrics.setdefault(name, []).append(value)

    def maybe_log(self) -> None:
        if not self.enabled:
            return

        now = time.perf_counter()
        if now - self._window_started_at < self._config.interval_s:
            return

        with self._lock:
            window_s = now - self._window_started_at
            metrics = self._metrics
            self._metrics = {}
            self._window_started_at = now

        if not metrics:
            logger.info("ocr_profile_summary scope=all window_s=%.2f empty=true", window_s)
            return

        logger.info("ocr_profile_summary scope=all %s", _format_summary(window_s, metrics))
        scoped_metrics = _group_metrics_by_scope(metrics)
        for scope in sorted(scoped_metrics):
            _SCOPED_LOGGERS[scope].info(
                "ocr_profile_summary scope=%s %s",
                scope,
                _format_summary(window_s, scoped_metrics[scope]),
            )


def ocr_profiling_config_from_env(
    *,
    enabled: bool | None = None,
    interval_s: float | None = None,
) -> OcrProfilingConfig:
    return OcrProfilingConfig(
        enabled=enabled if enabled is not None else _env_bool("ZML_OCR_PROFILING", default=False),
        interval_s=max(
            0.1,
            interval_s
            if interval_s is not None
            else _env_float("ZML_OCR_PROFILING_INTERVAL_S", default=10.0),
        ),
    )


def _format_metric(name: str, values: list[float]) -> str:
    count = len(values)
    avg = sum(values) / count
    maximum = max(values)
    p95 = _percentile(values, 0.95)
    return (
        f"{name}_count={count} "
        f"{name}_avg_ms={avg:.2f} "
        f"{name}_p95_ms={p95:.2f} "
        f"{name}_max_ms={maximum:.2f}"
    )


def _format_summary(window_s: float, metrics: dict[str, list[float]]) -> str:
    parts = [f"window_s={window_s:.2f}"]
    for name in sorted(metrics):
        parts.append(_format_metric(name, metrics[name]))
    return " ".join(parts)


def _group_metrics_by_scope(metrics: dict[str, list[float]]) -> dict[str, dict[str, list[float]]]:
    grouped: dict[str, dict[str, list[float]]] = {}
    for name, values in metrics.items():
        scope = _metric_scope(name)
        if scope is None:
            continue
        grouped.setdefault(scope, {})[name] = values
    return grouped


def _metric_scope(name: str) -> str | None:
    prefix, _, _ = name.partition(".")
    if prefix in _SCOPED_LOGGERS:
        return prefix
    return None


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percentile)))
    return ordered[index]


def _env_bool(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, *, default: float) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default
