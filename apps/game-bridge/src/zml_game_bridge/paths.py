from __future__ import annotations

import os
import sys
from pathlib import Path


def get_bridge_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def get_frozen_base_candidates() -> list[Path]:
    candidates: list[Path] = []

    pyinstaller_bundle_dir = getattr(sys, "_MEIPASS", None)
    if pyinstaller_bundle_dir:
        candidates.append(Path(pyinstaller_bundle_dir).resolve())

    candidates.append(Path(sys.executable).resolve().parent)

    return candidates


def get_tessdata_dir(explicit_path: str | None = None) -> Path:
    candidates: list[Path] = []

    if explicit_path:
        candidates.append(Path(explicit_path))

    env_path = os.environ.get("TESSDATA_PREFIX")
    if env_path:
        candidates.append(Path(env_path))

    if getattr(sys, "frozen", False):
        for base_dir in get_frozen_base_candidates():
            candidates.extend(
                [
                    base_dir / "tessdata",
                    base_dir / "resources" / "tessdata",
                    base_dir / "_internal" / "tessdata",
                    base_dir / "_internal" / "resources" / "tessdata",
                ]
            )
    else:
        project_root = get_bridge_project_root()
        candidates.extend(
            [
                project_root / "resources" / "tessdata",
                project_root / "tessdata",
            ]
        )

    for candidate in candidates:
        if (candidate / "eng.traineddata").exists():
            return candidate

    checked_paths = "\n".join(str(candidate) for candidate in candidates)
    raise RuntimeError(f"tessdata directory not found. Checked:\n{checked_paths}")