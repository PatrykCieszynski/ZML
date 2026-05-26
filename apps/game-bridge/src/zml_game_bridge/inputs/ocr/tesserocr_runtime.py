from __future__ import annotations

import importlib
from typing import Any


def preload_tesserocr() -> Any:
    try:
        return importlib.import_module("tesserocr")
    except Exception as exc:
        raise RuntimeError(f"tesserocr import failed: {exc}") from exc
