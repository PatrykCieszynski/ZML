from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from zml_ocr_worker.calibration.model import LocatedCompass
from zml_ocr_worker.capture.model import RoiRect
from zml_ocr_worker.pipelines.position.model import CoordinateRois
from zml_ocr_worker.runtime.paths import get_app_data_dir

logger = logging.getLogger(__name__)

_STATE_VERSION = 1


@dataclass(frozen=True, slots=True)
class PersistedCompassCalibration:
    frame_width: int
    frame_height: int
    compass: LocatedCompass
    rois: CoordinateRois


class CompassCalibrationStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_compass_calibration_path()

    def load(self) -> PersistedCompassCalibration | None:
        if not self.path.exists():
            return None
        try:
            payload: object = json.loads(self.path.read_text(encoding="utf-8"))
            return _state_from_json(payload)
        except Exception:
            logger.warning(
                "compass_calibration_state_load_failed path=%s",
                self.path,
                exc_info=True,
            )
            return None

    def save(self, state: PersistedCompassCalibration) -> bool:
        temp_path = self.path.with_name(f"{self.path.name}.tmp")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp_path.write_text(
                json.dumps(_state_to_json(state), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(temp_path, self.path)
        except OSError:
            logger.warning(
                "compass_calibration_state_write_failed path=%s",
                self.path,
                exc_info=True,
            )
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            return False
        logger.info("compass_calibration_state_saved path=%s", self.path)
        return True

    def clear(self) -> bool:
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            logger.warning(
                "compass_calibration_state_clear_failed path=%s",
                self.path,
                exc_info=True,
            )
            return False
        return True


def default_compass_calibration_path() -> Path:
    configured = os.getenv("ZML_COMPASS_CALIBRATION_PATH")
    if configured is not None and configured.strip() != "":
        return Path(configured)
    return get_app_data_dir() / "config" / "compass_calibration.json"


def _state_to_json(state: PersistedCompassCalibration) -> dict[str, object]:
    compass = state.compass
    return {
        "version": _STATE_VERSION,
        "frame": {
            "width": state.frame_width,
            "height": state.frame_height,
        },
        "compass": {
            "rect": _rect_to_json(compass.rect),
            "confidence": compass.confidence,
            "scale": compass.scale,
            "center_x": compass.center_x,
            "center_y": compass.center_y,
            "radius": compass.radius,
        },
        "coordinates": {
            "lon": _rect_to_json(state.rois.lon),
            "lat": _rect_to_json(state.rois.lat),
            "extract_numeric_tokens": state.rois.extract_numeric_tokens,
        },
    }


def _state_from_json(value: object) -> PersistedCompassCalibration:
    payload = _object(value)
    if _required_int(payload, "version") != _STATE_VERSION:
        raise ValueError("Unsupported compass calibration state version")

    frame = _object(payload.get("frame"))
    frame_width = _required_positive_int(frame, "width")
    frame_height = _required_positive_int(frame, "height")

    compass_payload = _object(payload.get("compass"))
    compass = LocatedCompass(
        rect=_rect_from_json(compass_payload.get("rect")),
        confidence=_required_float(compass_payload, "confidence", minimum=0.0, maximum=1.0),
        scale=_required_float(compass_payload, "scale", minimum=0.0),
        center_x=_required_float(compass_payload, "center_x"),
        center_y=_required_float(compass_payload, "center_y"),
        radius=_required_float(compass_payload, "radius", minimum=0.0),
    )
    if compass.scale <= 0.0 or compass.radius <= 0.0:
        raise ValueError("Compass scale and radius must be positive")

    coordinates = _object(payload.get("coordinates"))
    extract_numeric_tokens = coordinates.get("extract_numeric_tokens", False)
    if not isinstance(extract_numeric_tokens, bool):
        raise ValueError("extract_numeric_tokens must be a boolean")
    rois = CoordinateRois(
        lon=_rect_from_json(coordinates.get("lon")),
        lat=_rect_from_json(coordinates.get("lat")),
        extract_numeric_tokens=extract_numeric_tokens,
    )
    return PersistedCompassCalibration(
        frame_width=frame_width,
        frame_height=frame_height,
        compass=compass,
        rois=rois,
    )


def _rect_to_json(rect: RoiRect) -> dict[str, int]:
    return {
        "x1": rect.x1,
        "x2": rect.x2,
        "y1": rect.y1,
        "y2": rect.y2,
    }


def _rect_from_json(value: object) -> RoiRect:
    payload = _object(value)
    rect = RoiRect(
        x1=_required_non_negative_int(payload, "x1"),
        x2=_required_positive_int(payload, "x2"),
        y1=_required_non_negative_int(payload, "y1"),
        y2=_required_positive_int(payload, "y2"),
    )
    if rect.x2 <= rect.x1 or rect.y2 <= rect.y1:
        raise ValueError("Calibration rectangle must have positive width and height")
    return rect


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("Expected JSON object")
    return cast(dict[str, object], value)


def _required_int(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{key} must be an integer")
    return value


def _required_non_negative_int(payload: dict[str, object], key: str) -> int:
    value = _required_int(payload, key)
    if value < 0:
        raise ValueError(f"{key} must be non-negative")
    return value


def _required_positive_int(payload: dict[str, object], key: str) -> int:
    value = _required_int(payload, key)
    if value <= 0:
        raise ValueError(f"{key} must be positive")
    return value


def _required_float(
    payload: dict[str, object],
    key: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{key} must be numeric")
    number = float(value)
    if minimum is not None and number < minimum:
        raise ValueError(f"{key} must be >= {minimum}")
    if maximum is not None and number > maximum:
        raise ValueError(f"{key} must be <= {maximum}")
    return number
