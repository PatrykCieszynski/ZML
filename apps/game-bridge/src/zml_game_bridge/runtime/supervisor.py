from __future__ import annotations

import logging
from collections.abc import Callable
from threading import Thread
from typing import Any

from zml_game_bridge.runtime.worker_health import HealthDetail, WorkerHealthRegistry

logger = logging.getLogger(__name__)


class WorkerSupervisor:
    """Owns runtime worker threads and their health state."""

    def __init__(self, health: WorkerHealthRegistry | None = None) -> None:
        self._health = health or WorkerHealthRegistry()
        self._threads: dict[str, Thread] = {}

    def register(self, name: str, *, enabled: bool) -> None:
        self._health.register(name, enabled=enabled)

    def health(self) -> dict[str, object]:
        return self._health.as_dict()

    def mark_crashed(self, name: str, exc: BaseException) -> None:
        self._health.mark_crashed(name, exc)

    def mark_running(self, name: str) -> None:
        self._health.mark_running(name)

    def mark_degraded(self, name: str, message: str) -> None:
        self._health.mark_degraded(name, message)

    def update_details(self, name: str, **details: HealthDetail) -> None:
        self._health.update_details(name, **details)

    def start_thread(
        self,
        *,
        name: str,
        target: Callable[..., None],
        worker_kwargs: dict[str, Any],
    ) -> Thread:
        thread = Thread(
            target=self._run_worker,
            kwargs={"name": name, "target": target, "worker_kwargs": worker_kwargs},
            daemon=True,
        )
        self._threads[name] = thread
        thread.start()
        return thread

    def join_thread(self, name: str, *, timeout_s: float = 5.0) -> bool:
        thread = self._threads.get(name)
        if thread is None:
            return True
        thread.join(timeout=timeout_s)
        if thread.is_alive():
            logger.warning("runtime_thread_did_not_stop thread=%s", name)
            self._health.mark_degraded(name, "worker did not stop within 5s")
            return False
        return True

    def _run_worker(
        self,
        *,
        name: str,
        target: Callable[..., None],
        worker_kwargs: dict[str, Any],
    ) -> None:
        self._health.mark_running(name)
        try:
            target(**worker_kwargs)
        except Exception as exc:
            self._health.mark_crashed(name, exc)
            raise
        stop_event = worker_kwargs.get("stop_event")
        if stop_event is not None and stop_event.is_set():
            self._health.mark_stopped(name)
        else:
            self._health.mark_degraded(name, "worker returned before runtime shutdown")
