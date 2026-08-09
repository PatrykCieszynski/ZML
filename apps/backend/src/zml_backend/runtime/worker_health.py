from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass
from typing import Literal

WorkerState = Literal["running", "degraded", "crashed", "stopped"]
HealthDetail = str | int | float | bool | None


@dataclass(frozen=True, slots=True)
class WorkerHealthSnapshot:
    state: WorkerState
    enabled: bool
    last_error: str | None
    last_seen_ts_ms: int
    details: dict[str, HealthDetail]


class WorkerHealthRegistry:
    """Thread-safe in-memory health state for long-running runtime workers."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._workers: dict[str, WorkerHealthSnapshot] = {}

    def register(self, name: str, *, enabled: bool) -> None:
        with self._lock:
            self._workers[name] = WorkerHealthSnapshot(
                state="stopped",
                enabled=enabled,
                last_error=None,
                last_seen_ts_ms=_now_ms(),
                details={},
            )

    def mark_running(self, name: str) -> None:
        self._set_state(name, state="running", last_error=None)

    def mark_stopped(self, name: str) -> None:
        self._set_state(name, state="stopped", last_error=None)

    def mark_degraded(self, name: str, message: str) -> None:
        self._set_state(name, state="degraded", last_error=message)

    def mark_crashed(self, name: str, error: BaseException) -> None:
        self._set_state(name, state="crashed", last_error=f"{type(error).__name__}: {error}")

    def update_details(self, name: str, **details: HealthDetail) -> None:
        with self._lock:
            previous = self._workers.get(name)
            if previous is None:
                previous = WorkerHealthSnapshot(
                    state="stopped",
                    enabled=True,
                    last_error=None,
                    last_seen_ts_ms=_now_ms(),
                    details={},
                )
            merged = dict(previous.details)
            merged.update(details)
            self._workers[name] = WorkerHealthSnapshot(
                state=previous.state,
                enabled=previous.enabled,
                last_error=previous.last_error,
                last_seen_ts_ms=_now_ms(),
                details=merged,
            )

    def snapshot(self) -> dict[str, WorkerHealthSnapshot]:
        with self._lock:
            return dict(self._workers)

    def as_dict(self) -> dict[str, object]:
        workers = self.snapshot()
        return {
            "status": _overall_status(workers),
            "workers": {name: asdict(worker) for name, worker in workers.items()},
        }

    def _set_state(
        self,
        name: str,
        *,
        state: WorkerState,
        last_error: str | None,
    ) -> None:
        with self._lock:
            previous = self._workers.get(name)
            enabled = previous.enabled if previous is not None else True
            details = dict(previous.details) if previous is not None else {}
            self._workers[name] = WorkerHealthSnapshot(
                state=state,
                enabled=enabled,
                last_error=last_error,
                last_seen_ts_ms=_now_ms(),
                details=details,
            )


def _overall_status(workers: dict[str, WorkerHealthSnapshot]) -> WorkerState:
    enabled_workers = [worker for worker in workers.values() if worker.enabled]
    if not enabled_workers:
        return "stopped"
    if any(worker.state == "crashed" for worker in enabled_workers):
        return "crashed"
    if any(worker.state == "degraded" for worker in enabled_workers):
        return "degraded"
    if any(worker.state == "running" for worker in enabled_workers):
        return "running"
    return "stopped"


def _now_ms() -> int:
    return time.time_ns() // 1_000_000
