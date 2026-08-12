from __future__ import annotations

import base64
import json
import os
import signal
import subprocess
from pathlib import Path
from typing import Any

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
    health = runtime.health()
    workers = health.get("workers")
    if not isinstance(workers, dict):
        raise HTTPException(status_code=409, detail="OCR worker health is unavailable")
    worker = workers.get("ocr_worker")
    if not isinstance(worker, dict):
        raise HTTPException(status_code=409, detail="OCR worker is unavailable")
    details = worker.get("details")
    if not isinstance(details, dict):
        raise HTTPException(status_code=409, detail="OCR worker process details are unavailable")

    raw_pid = details.get("pid") or details.get("agent_pid")
    if not isinstance(raw_pid, int) or raw_pid <= 0:
        raise HTTPException(status_code=409, detail="OCR worker process is not running")

    try:
        os.kill(raw_pid, signal.SIGTERM)
    except OSError as exc:
        raise HTTPException(status_code=503, detail=f"Failed to restart OCR worker: {exc}") from exc

    return {
        "ok": True,
        "workerPid": raw_pid,
        "message": "OCR worker restart requested; automatic calibration will run after restart",
    }


def _snapshot_command(settings: Settings, *, output_dir: Path) -> list[str]:
    executable = (
        str(settings.ocr_worker_path) if settings.ocr_worker_path is not None else "zml-ocr-worker"
    )
    command = [
        executable,
        "calibration-snapshot",
        "--output-dir",
        str(output_dir),
    ]
    if settings.ocr_profile_path is not None:
        command.extend(["--profile", str(settings.ocr_profile_path)])
    return command


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
        if isinstance(metadata.get("innerRects"), dict)
        else {},
    }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _rect(value: object) -> list[int] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    if not all(isinstance(item, int) for item in value):
        return None
    return value


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


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
