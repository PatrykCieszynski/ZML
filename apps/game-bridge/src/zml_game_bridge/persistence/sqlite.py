from __future__ import annotations

import sqlite3
from pathlib import Path


def open_sqlite(
    db_path: Path | str,
    *,
    check_same_thread: bool = True,
) -> sqlite3.Connection:
    """Open sqlite connection with standard pragmas."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=check_same_thread)
    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")

    return conn
