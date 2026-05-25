from __future__ import annotations

import sqlite3
from pathlib import Path
from warnings import deprecated


def open_writer_connection(
    db_path: Path | str,
    *,
    check_same_thread: bool = True,
) -> sqlite3.Connection:
    """Open the single writer connection and apply writer pragmas."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=check_same_thread)
    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    _apply_common_pragmas(conn)

    return conn


def open_read_connection(
    db_path: Path | str,
    *,
    check_same_thread: bool = False,
) -> sqlite3.Connection:
    """Open a read-only connection for API/read-side queries."""
    path = Path(db_path).resolve()
    conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, check_same_thread=check_same_thread)
    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA query_only=ON")
    _apply_common_pragmas(conn)

    return conn


@deprecated("Legacy test compatibility only. Kept for tests and older call sites.")
def open_sqlite(
    db_path: Path | str,
    *,
    check_same_thread: bool = True,
) -> sqlite3.Connection:
    """Open a writer connection.
    """
    return open_writer_connection(db_path, check_same_thread=check_same_thread)


def _apply_common_pragmas(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
