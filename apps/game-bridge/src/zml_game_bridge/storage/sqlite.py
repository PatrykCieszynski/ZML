from __future__ import annotations

import sqlite3
from pathlib import Path


def open_sqlite(db_path: Path) -> sqlite3.Connection:
    """Open sqlite connection with standard pragmas."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")

    return conn
