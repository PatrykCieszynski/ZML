from __future__ import annotations

import threading
from typing import Any, cast

from zml_game_bridge.runtime.supervisor import WorkerSupervisor
from zml_game_bridge.runtime.worker_health import WorkerHealthRegistry


def test_worker_health_registry_reports_running_status() -> None:
    registry = WorkerHealthRegistry()
    registry.register("db_writer", enabled=True)

    registry.mark_running("db_writer")

    snapshot = registry.as_dict()
    workers = cast(dict[str, dict[str, Any]], snapshot["workers"])
    assert snapshot["status"] == "running"
    assert workers["db_writer"]["state"] == "running"
    assert workers["db_writer"]["last_error"] is None


def test_worker_health_registry_reports_crashed_status() -> None:
    registry = WorkerHealthRegistry()
    registry.register("db_writer", enabled=True)
    registry.register("ocr_worker", enabled=False)

    registry.mark_crashed("db_writer", RuntimeError("boom"))

    snapshot = registry.as_dict()
    workers = cast(dict[str, dict[str, Any]], snapshot["workers"])
    assert snapshot["status"] == "crashed"
    assert workers["db_writer"]["state"] == "crashed"
    assert workers["db_writer"]["last_error"] == "RuntimeError: boom"
    assert workers["ocr_worker"]["enabled"] is False


def test_worker_supervisor_marks_worker_stopped_after_clean_return() -> None:
    supervisor = WorkerSupervisor()
    stop_event = threading.Event()
    supervisor.register("worker", enabled=True)

    def worker(*, stop_event: threading.Event) -> None:
        stop_event.wait(timeout=1.0)

    thread = supervisor.start_thread(
        name="worker",
        target=worker,
        worker_kwargs={"stop_event": stop_event},
    )

    stop_event.set()
    thread.join(timeout=1.0)

    snapshot = supervisor.health()
    workers = cast(dict[str, dict[str, Any]], snapshot["workers"])
    assert workers["worker"]["state"] == "stopped"
