from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from zml_ocr_worker.calibration.model import LocatedCompass
from zml_ocr_worker.pipelines.position.model import CoordinateRois
from zml_ocr_worker.pipelines.position.pipeline import PositionReadResult
from zml_ocr_worker.pipelines.position.token_extractor import (
    NumericTokenAnalysis,
    NumericTokenExtractor,
)
from zml_ocr_worker.runtime.paths import get_app_data_dir


@dataclass(frozen=True, slots=True)
class CalibrationSnapshotConfig:
    enabled: bool
    root_dir: Path
    interval_ms: int = 2_000
    max_samples: int = 20

    @property
    def should_record(self) -> bool:
        return self.enabled and self.max_samples > 0


class CalibrationSnapshotRecorder:
    """Write local visual diagnostics for auto-calibrated coordinate OCR.

    Only the detected Compass crop is stored, not the full game frame. Each sample
    contains an annotated overview plus the exact line/token crops used by the
    coordinate pipeline so live geometry and token extraction can be inspected
    without guessing from logs.
    """

    def __init__(
        self,
        *,
        config: CalibrationSnapshotConfig,
        token_extractor: NumericTokenExtractor | None = None,
    ) -> None:
        self._config = config
        self._token_extractor = token_extractor or NumericTokenExtractor()
        self._last_recorded_ts_ms: int | None = None
        self._recorded_count = 0
        if config.should_record:
            config.root_dir.mkdir(parents=True, exist_ok=True)

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
        if not self._config.should_record:
            return None
        if self._recorded_count >= self._config.max_samples:
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

        lon_analysis = self._token_extractor.analyze(lon_line)
        lat_analysis = self._token_extractor.analyze(lat_line)

        sample_dir = self._config.root_dir / f"sample-{ts_ms}"
        sample_dir.mkdir(parents=True, exist_ok=True)

        overview = np.ascontiguousarray(compass_roi.copy())
        _draw_roi(overview, rois.lon, label="Lon line", line_index=0)
        _draw_roi(overview, rois.lat, label="Lat line", line_index=1)
        _draw_token(overview, rois.lon, lon_analysis, label="Lon token", line_index=2)
        _draw_token(overview, rois.lat, lat_analysis, label="Lat token", line_index=3)
        _draw_status(
            overview,
            layout_index=layout_index,
            read=read,
            compass=compass,
        )

        _write_png(sample_dir / "overview.png", overview)
        _write_png(sample_dir / "lon-line.png", lon_line)
        _write_png(sample_dir / "lat-line.png", lat_line)
        _write_png(sample_dir / "lon-mask.png", lon_analysis.mask)
        _write_png(sample_dir / "lat-mask.png", lat_analysis.mask)
        if lon_analysis.token is not None:
            _write_png(sample_dir / "lon-token.png", lon_analysis.token)
        if lat_analysis.token is not None:
            _write_png(sample_dir / "lat-token.png", lat_analysis.token)
        (sample_dir / "meta.txt").write_text(
            _metadata_text(
                compass=compass,
                rois=rois,
                read=read,
                layout_index=layout_index,
                lon_analysis=lon_analysis,
                lat_analysis=lat_analysis,
                ts_ms=ts_ms,
            ),
            encoding="utf-8",
        )

        # Keep one easy-to-find copy in addition to timestamped samples.
        _write_png(self._config.root_dir / "latest-overview.png", overview)
        _write_png(self._config.root_dir / "latest-lon-line.png", lon_line)
        _write_png(self._config.root_dir / "latest-lat-line.png", lat_line)
        _write_png(self._config.root_dir / "latest-lon-mask.png", lon_analysis.mask)
        _write_png(self._config.root_dir / "latest-lat-mask.png", lat_analysis.mask)
        if lon_analysis.token is not None:
            _write_png(self._config.root_dir / "latest-lon-token.png", lon_analysis.token)
        if lat_analysis.token is not None:
            _write_png(self._config.root_dir / "latest-lat-token.png", lat_analysis.token)
        (self._config.root_dir / "latest-meta.txt").write_text(
            (sample_dir / "meta.txt").read_text(encoding="utf-8"),
            encoding="utf-8",
        )

        self._last_recorded_ts_ms = ts_ms
        self._recorded_count += 1
        return sample_dir


def calibration_snapshot_config_from_env() -> CalibrationSnapshotConfig:
    return CalibrationSnapshotConfig(
        enabled=_env_bool("ZML_OCR_AUTO_CALIBRATION_SNAPSHOTS", default=False),
        root_dir=_env_path("ZML_OCR_AUTO_CALIBRATION_SNAPSHOT_DIR")
        or default_calibration_snapshot_dir(),
        interval_ms=_seconds_to_ms(
            _env_float("ZML_OCR_AUTO_CALIBRATION_SNAPSHOT_INTERVAL_S", default=2.0)
        ),
        max_samples=_env_int("ZML_OCR_AUTO_CALIBRATION_SNAPSHOT_MAX_SAMPLES", default=20),
    )


def default_calibration_snapshot_dir() -> Path:
    return get_app_data_dir() / "ocr" / "auto-calibration"


def _draw_roi(
    image: np.ndarray,
    roi,
    *,
    label: str,
    line_index: int,
) -> None:
    cv2.rectangle(image, (roi.x1, roi.y1), (roi.x2, roi.y2), (80, 220, 80), 1)
    _put_label(image, label, roi.x1, roi.y1, line_index=line_index)


def _draw_token(
    image: np.ndarray,
    line_roi,
    analysis: NumericTokenAnalysis,
    *,
    label: str,
    line_index: int,
) -> None:
    if analysis.x1 is None or analysis.x2 is None:
        return
    x1 = line_roi.x1 + analysis.x1
    x2 = line_roi.x1 + analysis.x2
    cv2.rectangle(image, (x1, line_roi.y1), (x2, line_roi.y2), (0, 220, 255), 1)
    _put_label(image, label, x1, line_roi.y2, line_index=line_index)


def _draw_status(
    image: np.ndarray,
    *,
    layout_index: int,
    read: PositionReadResult,
    compass: LocatedCompass,
) -> None:
    text = (
        f"layout={layout_index} lon={read.longitude} lat={read.latitude} "
        f"conf={_format_confidence(read.confidence)} radius={compass.radius:.1f}"
    )
    cv2.rectangle(image, (0, 0), (min(image.shape[1] - 1, 500), 24), (0, 0, 0), -1)
    cv2.putText(
        image,
        text,
        (5, 17),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.42,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )


def _put_label(image: np.ndarray, label: str, x: int, y: int, *, line_index: int) -> None:
    label_y = max(14, min(image.shape[0] - 4, y - 4 + line_index * 2))
    cv2.putText(
        image,
        label,
        (max(2, x), label_y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.38,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )


def _metadata_text(
    *,
    compass: LocatedCompass,
    rois: CoordinateRois,
    read: PositionReadResult,
    layout_index: int,
    lon_analysis: NumericTokenAnalysis,
    lat_analysis: NumericTokenAnalysis,
    ts_ms: int,
) -> str:
    return "\n".join(
        [
            f"ts_ms={ts_ms}",
            f"layout_index={layout_index}",
            f"compass_rect=({compass.rect.x1},{compass.rect.y1},{compass.rect.x2},{compass.rect.y2})",
            f"compass_center=({compass.center_x:.2f},{compass.center_y:.2f})",
            f"compass_radius={compass.radius:.2f}",
            f"compass_scale={compass.scale:.4f}",
            f"compass_confidence={compass.confidence:.4f}",
            f"lon_roi=({rois.lon.x1},{rois.lon.y1},{rois.lon.x2},{rois.lon.y2})",
            f"lat_roi=({rois.lat.x1},{rois.lat.y1},{rois.lat.x2},{rois.lat.y2})",
            f"lon_token=({lon_analysis.x1},{lon_analysis.x2})",
            f"lat_token=({lat_analysis.x1},{lat_analysis.x2})",
            f"ocr_lon={read.longitude}",
            f"ocr_lat={read.latitude}",
            f"ocr_confidence={_format_confidence(read.confidence)}",
            "",
        ]
    )


def _write_png(path: Path, image: np.ndarray) -> None:
    if not cv2.imwrite(str(path), image):
        raise RuntimeError(f"Failed to write OCR calibration snapshot: {path}")


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
