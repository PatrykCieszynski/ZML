from __future__ import annotations

import importlib
import signal
from typing import Any


def preload_tesserocr() -> Any:
    try:
        return importlib.import_module("tesserocr")
    except Exception as exc:
        raise RuntimeError(f"tesserocr import failed: {exc}") from exc


def preload_tesserocr_preserving_sigint_handler() -> Any:
    """Import tesserocr on the main thread without replacing Uvicorn's Ctrl+C handler."""
    previous_handler = signal.getsignal(signal.SIGINT)
    try:
        return preload_tesserocr()
    finally:
        if previous_handler is not None:
            signal.signal(signal.SIGINT, previous_handler)
