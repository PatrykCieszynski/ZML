from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from zml_ocr_worker.runtime.paths import get_app_data_dir

logger = logging.getLogger(__name__)
_SCOPED_LOGGERS = {
    "position": logging.getLogger(f"{__name__}.position"),
    "finder": logging.getLogger(f"{__name__}.finder"),
    "deed": logging.getLogger(f"{__name__}.deed"),
}


@dataclass(frozen=True, slots=True)
class OcrProfilingConfig:
    enabled: bool = True
    interval_s: float = 10.0
    health_path: Path | None = None

    @property
    def resolved_health_path(self) -> Path:
        return self.health_path or (get_app_data_dir() / "ocr" / "health.json")


class OcrProfiler:
    """Collect bounded OCR timing/counter health data and persist the latest window."""

    def __init__(self, *, config: OcrProfilingConfig) -> None:
        self._config = config
        self._lock = threading.Lock()
        self._window_started_at = time.perf_counter()
        self._started_at = self._window_started_at
        self._metrics: dict[str, list[float]] = {}
        self._counters: dict[str, int] = {}
        self._lifetime_counters: dict[str, int] = {}

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

    def increment(self, name: str, amount: int = 1) -> None:
        if not self.enabled or amount == 0:
            return
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + amount
            self._lifetime_counters[name] = self._lifetime_counters.get(name, 0) + amount

    def maybe_log(self) -> None:
        if not self.enabled:
            return

        now = time.perf_counter()
        if now - self._window_started_at < self._config.interval_s:
            return

        with self._lock:
            window_s = now - self._window_started_at
            metrics = self._metrics
            counters = self._counters
            lifetime_counters = dict(self._lifetime_counters)
            self._metrics = {}
            self._counters = {}
            self._window_started_at = now

        summary = _format_summary(window_s, metrics, counters)
        logger.info("ocr_health_summary scope=all %s", summary)
        scoped_metrics = _group_by_scope(metrics)
        scoped_counters = _group_by_scope(counters)
        for scope in sorted(set(scoped_metrics) | set(scoped_counters)):
            _SCOPED_LOGGERS[scope].info(
                "ocr_health_summary scope=%s %s",
                scope,
                _format_summary(
                    window_s,
                    scoped_metrics.get(scope, {}),
                    scoped_counters.get(scope, {}),
                ),
            )

        try:
            _write_health_snapshot(
                self._config.resolved_health_path,
                window_s=window_s,
                uptime_s=now - self._started_at,
                metrics=metrics,
                counters=counters,
                lifetime_counters=lifetime_counters,
            )
        except Exception:
            logger.warning(
                "ocr_health_snapshot_write_failed path=%s",
                self._config.resolved_health_path,
                exc_info=True,
            )


def ocr_profiling_config_from_env(
    *,
    enabled: bool | None = None,
    interval_s: float | None = None,
) -> OcrProfilingConfig:
    # Health statistics are intentionally on by default in releases. The old bridge
    # config used ``false`` as its default profiling value, so only an explicit worker
    # environment override disables the new lightweight health snapshot.
    env_enabled = _env_optional_bool("ZML_OCR_PROFILING")
    resolved_enabled = env_enabled if env_enabled is not None else True
    if enabled is True:
        resolved_enabled = True

    return OcrProfilingConfig(
        enabled=resolved_enabled,
        interval_s=max(
            0.1,
            interval_s
            if interval_s is not None
            else _env_float("ZML_OCR_PROFILING_INTERVAL_S", default=10.0),
        ),
        health_path=_env_path("ZML_OCR_HEALTH_PATH"),
    )


def _format_metric(name: str, values: list[float]) -> str:
    summary = _metric_summary(values)
    return (
        f"{name}_count={summary['count']} "
        f"{name}_avg_ms={summary['avg_ms']:.2f} "
        f"{name}_p95_ms={summary['p95_ms']:.2f} "
        f"{name}_max_ms={summary['max_ms']:.2f}"
    )


def _format_summary(
    window_s: float,
    metrics: dict[str, list[float]],
    counters: dict[str, int],
) -> str:
    parts = [f"window_s={window_s:.2f}"]
    for name in sorted(counters):
        parts.append(f"{name}={counters[name]}")
    for name in sorted(metrics):
        parts.append(_format_metric(name, metrics[name]))
    if len(parts) == 1:
        parts.append("empty=true")
    return " ".join(parts)


def _group_by_scope[T](values: dict[str, T]) -> dict[str, dict[str, T]]:
    grouped: dict[str, dict[str, T]] = {}
    for name, value in values.items():
        scope = _metric_scope(name)
        if scope is None:
            continue
        grouped.setdefault(scope, {})[name] = value
    return grouped


def _metric_scope(name: str) -> str | None:
    prefix, _, _ = name.partition(".")
    if prefix in _SCOPED_LOGGERS:
        return prefix
    return None


def _metric_summary(values: list[float]) -> dict[str, float | int]:
    count = len(values)
    if count == 0:
        return {"count": 0, "avg_ms": 0.0, "p95_ms": 0.0, "max_ms": 0.0}
    return {
        "count": count,
        "avg_ms": sum(values) / count,
        "p95_ms": _percentile(values, 0.95),
        "max_ms": max(values),
    }


def _write_health_snapshot(
    path: Path,
    *,
    window_s: float,
    uptime_s: float,
    metrics: dict[str, list[float]],
    counters: dict[str, int],
    lifetime_counters: dict[str, int],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "updated_at": datetime.now(tz=UTC).isoformat(),
        "window_seconds": round(window_s, 3),
        "uptime_seconds": round(uptime_s, 3),
        "counters": dict(sorted(counters.items())),
        "lifetime_counters": dict(sorted(lifetime_counters.items())),
        "timings_ms": {
            name: _metric_summary(values) for name, values in sorted(metrics.items())
        },
    }
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    os.replace(temp_path, path)


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percentile)))
    return ordered[index]


def _env_optional_bool(name: str) -> bool | None:
    value = os.getenv(name)
    if value is None:
        return None
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, *, default: float) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_path(name: str) -> Path | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return None
    return Path(value)
