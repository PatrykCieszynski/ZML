from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from zml_ocr_worker.calibration.model import LocatedCompass
from zml_ocr_worker.pipelines.position.model import CoordinateRois
from zml_ocr_worker.pipelines.position.pipeline import PositionReadResult
from zml_ocr_worker.runtime.paths import get_app_data_dir

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CalibrationSnapshotConfig:
    """Bounded production diagnostics for suspicious coordinate OCR reads."""

    enabled: bool
    root_dir: Path
    interval_ms: int = 5_000
    max_samples: int = 20
    invalid_streak_threshold: int = 5
    low_confidence_threshold: float = 0.15
    digit_count_confirm_frames: int = 5

    @property
    def should_record(self) -> bool:
        return self.enabled and self.max_samples > 0


class CalibrationSnapshotRecorder:
    """Capture only suspicious coordinate reads, never the full game frame.

    Normal production reads do not touch disk. A bounded sample is written only when
    the numeric digit count unexpectedly changes, a run of invalid reads reaches the
    recovery threshold, or confidence first enters a very-low-confidence state.
    Samples contain the Compass crop plus the active Lon/Lat lines needed to improve
    OCR later; chat and the rest of the game frame are never recorded.
    """

    def __init__(self, *, config: CalibrationSnapshotConfig) -> None:
        self._config = config
        self._last_recorded_ts_ms: int | None = None
        self._expected_digit_counts: tuple[int, int] | None = None
        self._pending_digit_counts: tuple[int, int] | None = None
        self._pending_digit_count_streak = 0
        self._invalid_streak = 0
        self._low_confidence_active = False
        if config.should_record:
            config.root_dir.mkdir(parents=True, exist_ok=True)
            _prune_samples(config.root_dir, max_samples=config.max_samples)

    @property
    def root_dir(self) -> Path:
        return self._config.root_dir

    def record(
        self,
        compass_roi: np.ndarray,
        *,
        compass: LocatedCompass,
        rois: CoordinateRois,
        read: PositionReadResult,
        layout_index: int,
        ts_ms: int,
    ) -> Path | None:
        reason = self._suspect_reason(read)
        if reason is None or not self._config.should_record:
            return None
        if (
            self._last_recorded_ts_ms is not None
            and ts_ms - self._last_recorded_ts_ms < self._config.interval_ms
        ):
            return None

        lon_line = rois.lon.crop(compass_roi)
        lat_line = rois.lat.crop(compass_roi)
        if lon_line is None or lat_line is None:
            return None

        sample_dir = self._config.root_dir / f"sample-{ts_ms}-{reason}"
        sample_dir.mkdir(parents=True, exist_ok=True)

        overview = np.ascontiguousarray(compass_roi.copy())
        _draw_roi(overview, rois.lon, label="Lon digits", line_index=0)
        _draw_roi(overview, rois.lat, label="Lat digits", line_index=1)
        _draw_status(
            overview,
            reason=reason,
            layout_index=layout_index,
            read=read,
            compass=compass,
        )

        _write_png(sample_dir / "overview.png", overview)
        _write_png(sample_dir / "lon-line.png", lon_line)
        _write_png(sample_dir / "lat-line.png", lat_line)
        (sample_dir / "meta.txt").write_text(
            _metadata_text(
                reason=reason,
                compass=compass,
                rois=rois,
                read=read,
                layout_index=layout_index,
                ts_ms=ts_ms,
            ),
            encoding="utf-8",
        )

        self._last_recorded_ts_ms = ts_ms
        _prune_samples(self._config.root_dir, max_samples=self._config.max_samples)
        return sample_dir

    def _suspect_reason(self, read: PositionReadResult) -> str | None:
        if not read.valid:
            self._invalid_streak += 1
            self._low_confidence_active = False
            if self._invalid_streak == max(1, self._config.invalid_streak_threshold):
                return "repeated-invalid-read"
            return None

        self._invalid_streak = 0
        counts = _digit_counts(read)
        if counts is not None:
            if self._expected_digit_counts is None:
                self._expected_digit_counts = counts
            elif counts == self._expected_digit_counts:
                self._pending_digit_counts = None
                self._pending_digit_count_streak = 0
            elif counts == self._pending_digit_counts:
                self._pending_digit_count_streak += 1
                if self._pending_digit_count_streak >= max(
                    1, self._config.digit_count_confirm_frames
                ):
                    self._expected_digit_counts = counts
                    self._pending_digit_counts = None
                    self._pending_digit_count_streak = 0
            else:
                self._pending_digit_counts = counts
                self._pending_digit_count_streak = 1
                return "digit-count-changed"

        confidence = read.confidence
        low_confidence = (
            confidence is not None and confidence < self._config.low_confidence_threshold
        )
        if low_confidence and not self._low_confidence_active:
            self._low_confidence_active = True
            return "very-low-confidence"
        if not low_confidence:
            self._low_confidence_active = False
        return None


def calibration_snapshot_config_from_env() -> CalibrationSnapshotConfig:
    """Resolve the bounded suspect capture used in both development and releases."""

    return CalibrationSnapshotConfig(
        enabled=_env_bool("ZML_OCR_SUSPECT_CAPTURE", default=True),
        root_dir=_env_path("ZML_OCR_SUSPECT_CAPTURE_DIR") or default_calibration_snapshot_dir(),
        interval_ms=_seconds_to_ms(
            _env_float("ZML_OCR_SUSPECT_CAPTURE_COOLDOWN_S", default=5.0)
        ),
        max_samples=_env_int("ZML_OCR_SUSPECT_CAPTURE_MAX_SAMPLES", default=20),
    )


def default_calibration_snapshot_dir() -> Path:
    return get_app_data_dir() / "ocr" / "suspects"


def _digit_counts(read: PositionReadResult) -> tuple[int, int] | None:
    if not read.valid or read.longitude is None or read.latitude is None:
        return None
    return len(str(abs(read.longitude))), len(str(abs(read.latitude)))


def _draw_roi(
    image: np.ndarray,
    roi,
    *,
    label: str,
    line_index: int,
) -> None:
    cv2.rectangle(image, (roi.x1, roi.y1), (roi.x2, roi.y2), (80, 220, 80), 1)
    label_y = max(14, min(image.shape[0] - 4, roi.y1 - 4 + line_index * 2))
    cv2.putText(
        image,
        label,
        (max(2, roi.x1), label_y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.38,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )


def _draw_status(
    image: np.ndarray,
    *,
    reason: str,
    layout_index: int,
    read: PositionReadResult,
    compass: LocatedCompass,
) -> None:
    text = (
        f"reason={reason} layout={layout_index} lon={read.longitude} lat={read.latitude} "
        f"conf={_format_confidence(read.confidence)} radius={compass.radius:.1f}"
    )
    cv2.rectangle(image, (0, 0), (min(image.shape[1] - 1, 620), 24), (0, 0, 0), -1)
    cv2.putText(
        image,
        text,
        (5, 17),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.40,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )


def _metadata_text(
    *,
    reason: str,
    compass: LocatedCompass,
    rois: CoordinateRois,
    read: PositionReadResult,
    layout_index: int,
    ts_ms: int,
) -> str:
    return "\n".join(
        [
            f"ts_ms={ts_ms}",
            f"reason={reason}",
            f"layout_index={layout_index}",
            f"compass_rect=({compass.rect.x1},{compass.rect.y1},{compass.rect.x2},{compass.rect.y2})",
            f"compass_center=({compass.center_x:.2f},{compass.center_y:.2f})",
            f"compass_radius={compass.radius:.2f}",
            f"compass_scale={compass.scale:.4f}",
            f"compass_confidence={compass.confidence:.4f}",
            f"lon_roi=({rois.lon.x1},{rois.lon.y1},{rois.lon.x2},{rois.lon.y2})",
            f"lat_roi=({rois.lat.x1},{rois.lat.y1},{rois.lat.x2},{rois.lat.y2})",
            f"ocr_lon={read.longitude}",
            f"ocr_lat={read.latitude}",
            f"ocr_confidence={_format_confidence(read.confidence)}",
            "",
        ]
    )


def _prune_samples(root_dir: Path, *, max_samples: int) -> None:
    samples = sorted(
        (path for path in root_dir.glob("sample-*") if path.is_dir()),
        key=lambda path: path.stat().st_mtime_ns,
    )
    for sample in samples[: max(0, len(samples) - max(0, max_samples))]:
        shutil.rmtree(sample, ignore_errors=True)


def _write_png(path: Path, image: np.ndarray) -> None:
    if not cv2.imwrite(str(path), image):
        raise RuntimeError(f"Failed to write OCR suspect snapshot: {path}")


def _format_confidence(value: float | None) -> str:
    return "none" if value is None else f"{value:.3f}"


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
