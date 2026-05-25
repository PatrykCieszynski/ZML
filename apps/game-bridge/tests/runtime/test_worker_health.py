from __future__ import annotations

from typing import Any, cast

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
