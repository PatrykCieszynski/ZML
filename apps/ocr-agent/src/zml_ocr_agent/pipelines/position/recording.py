from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from zml_ocr_agent.pipelines.position.model import PositionRois
from zml_ocr_agent.runtime.paths import get_app_data_dir

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PositionRoiSnapshotConfig:
    enabled: bool
    root_dir: Path
    interval_ms: int = 60_000
    max_samples: int = 1

    @property
    def should_record(self) -> bool:
        return self.enabled and self.max_samples > 0


class PositionRoiSnapshotRecorder:
    def __init__(self, *, config: PositionRoiSnapshotConfig, rois: PositionRois) -> None:
        self._config = config
        self._rois = rois
        self._last_recorded_ts_ms: int | None = None
        self._recorded_count = 0
        if config.should_record:
            config.root_dir.mkdir(parents=True, exist_ok=True)

    def record(self, compass_roi: np.ndarray, *, ts_ms: int) -> None:
        if not self._config.should_record:
            return
        if self._recorded_count >= self._config.max_samples:
            return
        if (
            self._last_recorded_ts_ms is not None
            and ts_ms - self._last_recorded_ts_ms < self._config.interval_ms
        ):
            return

        try:
            lon_roi = self._rois.lon.crop(compass_roi)
            lat_roi = self._rois.lat.crop(compass_roi)
            self._write_png("compass.png", compass_roi)
            if lon_roi is not None:
                self._write_png("lon.png", lon_roi)
            if lat_roi is not None:
                self._write_png("lat.png", lat_roi)
            self._last_recorded_ts_ms = ts_ms
            self._recorded_count += 1
            logger.debug(
                "position_roi_snapshot_recorded dir=%s ts_ms=%s",
                self._config.root_dir,
                ts_ms,
            )
        except Exception:
            logger.warning("position_roi_snapshot_failed ts_ms=%s", ts_ms, exc_info=True)

    def _write_png(self, filename: str, image: np.ndarray) -> None:
        path = self._config.root_dir / filename
        if not cv2.imwrite(str(path), image):
            raise RuntimeError(f"Failed to write position ROI snapshot: {path}")


def position_roi_snapshot_config_from_env(
    *,
    enabled: bool | None = None,
    root_dir: Path | None = None,
    interval_s: float | None = None,
    max_samples: int | None = None,
) -> PositionRoiSnapshotConfig:
    return PositionRoiSnapshotConfig(
        enabled=enabled
        if enabled is not None
        else _env_bool("ZML_POSITION_ROI_SNAPSHOTS", default=False),
        root_dir=root_dir
        or _env_path("ZML_POSITION_ROI_SNAPSHOT_DIR")
        or default_position_roi_snapshot_dir(),
        interval_ms=_seconds_to_ms(
            interval_s
            if interval_s is not None
            else _env_float("ZML_POSITION_ROI_SNAPSHOT_INTERVAL_S", default=60.0)
        ),
        max_samples=max_samples
        if max_samples is not None
        else _env_int("ZML_POSITION_ROI_SNAPSHOT_MAX_SAMPLES", default=1),
    )


def default_position_roi_snapshot_dir() -> Path:
    return get_app_data_dir() / "ocr" / "position-roi"


def _env_bool(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_path(name: str) -> Path | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return None
    return Path(value)


def _env_float(name: str, *, default: float) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_int(name: str, *, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _seconds_to_ms(value: float) -> int:
    return max(1, int(value * 1000))
