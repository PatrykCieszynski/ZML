from __future__ import annotations

import os
import sys
from pathlib import Path

APP_DATA_DIR_NAME = "z-mining-log"


def get_agent_project_root() -> Path:
    return Path(__file__).resolve().parents[5]


def get_workspace_root() -> Path:
    return get_agent_project_root().parents[2]


def get_app_data_dir(explicit_path: str | Path | None = None) -> Path:
    if explicit_path is not None and str(explicit_path).strip() != "":
        return Path(explicit_path)

    env_path = os.environ.get("ZML_APP_DATA_DIR")
    if env_path is not None and env_path.strip() != "":
        return Path(env_path)

    if not getattr(sys, "frozen", False):
        return get_workspace_root() / ".tmp" / "appdata" / "ocr-worker"

    app_data = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or str(Path.home())
    return Path(app_data) / APP_DATA_DIR_NAME


def get_frozen_base_candidates() -> list[Path]:
    candidates: list[Path] = []
    pyinstaller_bundle_dir = getattr(sys, "_MEIPASS", None)
    if pyinstaller_bundle_dir:
        candidates.append(Path(pyinstaller_bundle_dir).resolve())
    candidates.append(Path(sys.executable).resolve().parent)
    return candidates


def get_tessdata_dir(explicit_path: str | Path | None = None) -> Path:
    candidates: list[Path] = []

    if explicit_path is not None and str(explicit_path).strip() != "":
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
        project_root = get_agent_project_root()
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
