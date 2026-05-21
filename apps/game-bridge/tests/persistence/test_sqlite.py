from __future__ import annotations

import threading
from pathlib import Path

from zml_game_bridge.persistence.sqlite import open_sqlite


def test_open_sqlite_default_connection_is_thread_bound(tmp_path: Path) -> None:
    conn = open_sqlite(tmp_path / "threaded-default.sqlite3")
    errors: list[BaseException] = []

    def use_connection() -> None:
        try:
            conn.execute("SELECT 1").fetchone()
        except BaseException as exc:
            errors.append(exc)

    try:
        thread = threading.Thread(target=use_connection)
        thread.start()
        thread.join(timeout=1.0)
    finally:
        conn.close()

    assert not thread.is_alive()
    assert errors != []


def test_open_sqlite_api_connection_can_be_used_from_fastapi_worker_thread(
    tmp_path: Path,
) -> None:
    conn = open_sqlite(tmp_path / "threaded-api.sqlite3", check_same_thread=False)
    errors: list[BaseException] = []

    def use_connection() -> None:
        try:
            conn.execute("SELECT 1").fetchone()
        except BaseException as exc:
            errors.append(exc)

    try:
        thread = threading.Thread(target=use_connection)
        thread.start()
        thread.join(timeout=1.0)
    finally:
        conn.close()

    assert not thread.is_alive()
    assert errors == []
