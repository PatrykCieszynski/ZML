from __future__ import annotations

import threading
from pathlib import Path

from zml_backend.persistence.sqlite import open_read_connection, open_sqlite


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


def test_open_read_connection_is_read_only(tmp_path: Path) -> None:
    db_path = tmp_path / "readonly.sqlite3"
    writer = open_sqlite(db_path)
    try:
        writer.execute("CREATE TABLE sample (value INTEGER NOT NULL)")
        writer.execute("INSERT INTO sample (value) VALUES (1)")
        writer.commit()
    finally:
        writer.close()

    errors: list[BaseException] = []
    reader = open_read_connection(db_path)
    try:
        row = reader.execute("SELECT value FROM sample").fetchone()
        assert row is not None
        assert row["value"] == 1

        try:
            reader.execute("INSERT INTO sample (value) VALUES (2)")
        except BaseException as exc:
            errors.append(exc)
    finally:
        reader.close()

    assert errors != []
