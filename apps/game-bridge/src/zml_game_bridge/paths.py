from __future__ import annotations

import os
import sys
from pathlib import Path


def get_bridge_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parents[2]


def get_tessdata_dir(explicit_path: str | None = None) -> Path:
    candidates: list[Path] = []

    if explicit_path:
        candidates.append(Path(explicit_path))

    env_path = os.environ.get("TESSDATA_PREFIX")
    if env_path:
        candidates.append(Path(env_path))

    base_dir = get_bridge_base_dir()
    candidates.extend(
        [
            base_dir / "tessdata",
            base_dir / "resources" / "tessdata",
        ]
    )

    for candidate in candidates:
        if (candidate / "eng.traineddata").exists():
            return candidate

    checked_paths = "\n".join(str(candidate) for candidate in candidates)
    raise RuntimeError(f"tessdata directory not found. Checked:\n{checked_paths}")