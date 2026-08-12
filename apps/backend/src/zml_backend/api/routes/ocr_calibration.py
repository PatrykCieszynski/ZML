from __future__ import annotations

import base64
import json
import os
import signal
import subprocess
from pathlib import Path
from typing import cast

from fastapi import APIRouter, HTTPException, Request

from zml_backend.runtime.runtime import AppRuntime
from zml_backend.settings import Settings

router = APIRouter(prefix="/api/v1/ocr/calibration", tags=["ocr-calibration"])


@router.get("")
def get_ocr_calibration(request: Request) -> dict[str, object]:
    settings = _settings(request)
    output_dir = settings.ocr_capture_artifacts_dir / "calibration-ui"
    output_dir.mkdir(parents=True, exist_ok=True)

    command = _snapshot_command(settings, output_dir=output_dir)
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(
            command,
            cwd=None,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            timeout=12.0,
            check=False,
            creationflags=creation_flags,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HTTPException(status_code=503, detail=f"Calibration snapshot failed: {exc}") from exc

    if completed.returncode != 0:
        detail = (
            completed.stderr.strip() or completed.stdout.strip() or "OCR snapshot command failed"
        )
        raise HTTPException(status_code=503, detail=detail[-1000:])

    snapshot_meta = _read_json(output_dir / "snapshot.json")
    captured_ts_ms = _optional_int(snapshot_meta.get("capturedTsMs"))
    return {
        "capturedTsMs": captured_ts_ms,
        "finder": _read_region(output_dir, "finder"),
        "compass": _read_region(output_dir, "compass"),
    }


@router.post("/recalibrate")
def recalibrate_ocr(request: Request) -> dict[str, object]:
    runtime = _runtime(request)
    settings = _settings(request)
    workers = _object_dict(runtime.health().get("workers"))
    if workers is None:
        raise HTTPException(status_code=409, detail="OCR worker health is unavailable")
    worker = _object_dict(workers.get("ocr_worker"))
    if worker is None:
        raise HTTPException(status_code=409, detail="OCR worker is unavailable")
    details = _object_dict(worker.get("details"))
    if details is None:
        raise HTTPException(status_code=409, detail="OCR worker process details are unavailable")

    raw_pid = details.get("pid") or details.get("agent_pid")
    if not isinstance(raw_pid, int) or isinstance(raw_pid, bool) or raw_pid <= 0:
        raise HTTPException(status_code=409, detail="OCR worker process is not running")

    calibration_path = _compass_calibration_path(settings)
    try:
        calibration_path.unlink(missing_ok=True)
    except OSError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Failed to clear persisted Compass calibration: {exc}",
        ) from exc

    try:
        os.kill(raw_pid, signal.SIGTERM)
    except OSError as exc:
        raise HTTPException(status_code=503, detail=f"Failed to restart OCR worker: {exc}") from exc

    return {
        "ok": True,
        "workerPid": raw_pid,
        "message": "OCR worker restart requested; Compass calibration will be rebuilt",
    }


def _snapshot_command(settings: Settings, *, output_dir: Path) -> list[str]:
    executable = (
        str(settings.ocr_worker_path) if settings.ocr_worker_path is not None else "zml-ocr-worker"
    )
    return [
        executable,
        "calibration-snapshot",
        "--output-dir",
        str(output_dir),
        "--profile",
        str(settings.ocr_profile_path),
    ]


def _compass_calibration_path(settings: Settings) -> Path:
    return settings.ocr_profile_path.with_name("compass_calibration.json")


def _read_region(output_dir: Path, region: str) -> dict[str, object]:
    png_path = output_dir / f"{region}.png"
    metadata = _read_json(output_dir / f"{region}.json")
    if not png_path.exists() or not metadata:
        return {"available": False}

    try:
        encoded = base64.b64encode(png_path.read_bytes()).decode("ascii")
    except OSError:
        return {"available": False}

    return {
        "available": True,
        "imageDataUrl": f"data:image/png;base64,{encoded}",
        "capturedTsMs": _optional_int(metadata.get("capturedTsMs")),
        "rect": _rect(metadata.get("rect")),
        "confidence": _optional_float(metadata.get("confidence")),
        "scale": _optional_float(metadata.get("scale")),
        "innerRects": metadata.get("innerRects")
        if _object_dict(metadata.get("innerRects")) is not None
        else {},
    }


def _read_json(path: Path) -> dict[str, object]:
    try:
        value: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    parsed = _object_dict(value)
    return parsed or {}


def _object_dict(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    return cast(dict[str, object], value)


def _rect(value: object) -> list[int] | None:
    if not isinstance(value, list):
        return None
    items = cast(list[object], value)
    if len(items) != 4:
        return None
    result: list[int] = []
    for item in items:
        if not isinstance(item, int) or isinstance(item, bool):
            return None
        result.append(item)
    return result


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _runtime(request: Request) -> AppRuntime:
    runtime = getattr(request.app.state, "runtime", None)
    if not isinstance(runtime, AppRuntime):
        raise HTTPException(status_code=503, detail="Runtime is unavailable")
    return runtime


def _settings(request: Request) -> Settings:
    settings = getattr(request.app.state, "settings", None)
    if not isinstance(settings, Settings):
        raise HTTPException(status_code=503, detail="Backend settings are unavailable")
    return settings
