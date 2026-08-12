from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import cv2
import numpy as np

from zml_ocr_worker.pipelines.mining_finder.model import (
    FinderFeatures,
    MiningFinderSignal,
)
from zml_ocr_worker.runtime.paths import get_app_data_dir

logger = logging.getLogger(__name__)

FinderRecordingMode = Literal["manual", "interval", "accepted"]
_VALID_MODES: set[FinderRecordingMode] = {
    "manual",
    "interval",
    "accepted",
}


@dataclass(frozen=True, slots=True)
class FinderRecordingConfig:
    modes: frozenset[FinderRecordingMode]
    root_dir: Path
    interval_ms: int = 60_000
    max_samples: int = 1
    manual_trigger_filename: str = "record-now.flag"

    @property
    def enabled(self) -> bool:
        return bool(self.modes) and self.max_samples > 0


class FinderCropRecorder:
    def __init__(
        self,
        *,
        config: FinderRecordingConfig,
        roi_name: str,
    ) -> None:
        self._config = config
        self._roi_name = roi_name
        self._last_interval_ts_ms: int | None = None
        self._sequence = 0
        if config.enabled:
            config.root_dir.mkdir(parents=True, exist_ok=True)

    def record_accepted_frame(
        self,
        finder_roi: np.ndarray,
        *,
        ts_ms: int,
    ) -> None:
        """Persist a Finder crop immediately before expensive feature OCR.

        The runtime has already located the panel and passed the visual presence guard
        at this point. Recording here guarantees that false-positive evidence survives
        even if the later Finder OCR is slow or raises an exception.
        """

        if not self._config.enabled or "accepted" not in self._config.modes:
            return
        if self._sequence >= self._config.max_samples:
            return
        try:
            self._write_sample(
                finder_roi,
                ts_ms=ts_ms,
                reasons=["accepted"],
                features=None,
                signals=[],
                phase="accepted_before_ocr",
            )
        except Exception:
            logger.warning("finder_crop_record_failed ts_ms=%s phase=accepted", ts_ms, exc_info=True)

    def record_frame(
        self,
        finder_roi: np.ndarray,
        *,
        ts_ms: int,
        features: FinderFeatures,
        signals: list[MiningFinderSignal],
    ) -> None:
        """Record interval/manual Finder diagnostics after feature OCR."""

        if not self._config.enabled:
            return
        if self._sequence >= self._config.max_samples:
            return

        try:
            reasons = self._post_ocr_recording_reasons(ts_ms=ts_ms)
            if not reasons:
                return

            self._write_sample(
                finder_roi,
                ts_ms=ts_ms,
                features=features,
                signals=signals,
                reasons=reasons,
                phase="after_ocr",
            )
        except Exception:
            logger.warning("finder_crop_record_failed ts_ms=%s phase=after_ocr", ts_ms, exc_info=True)

    def _post_ocr_recording_reasons(
        self,
        *,
        ts_ms: int,
    ) -> list[str]:
        reasons: list[str] = []

        if "manual" in self._config.modes and self._consume_manual_trigger():
            reasons.append("manual")

        if "interval" in self._config.modes and (
            self._last_interval_ts_ms is None
            or (ts_ms - self._last_interval_ts_ms >= self._config.interval_ms)
        ):
            self._last_interval_ts_ms = ts_ms
            reasons.append("interval")

        return reasons

    def _consume_manual_trigger(self) -> bool:
        trigger = self._config.root_dir / self._config.manual_trigger_filename
        if not trigger.exists():
            return False
        try:
            trigger.unlink()
        except OSError:
            logger.warning(
                "finder_record_manual_trigger_delete_failed path=%s", trigger, exc_info=True
            )
        return True

    def _write_sample(
        self,
        finder_roi: np.ndarray,
        *,
        ts_ms: int,
        reasons: list[str],
        features: FinderFeatures | None,
        signals: list[MiningFinderSignal],
        phase: str,
    ) -> None:
        self._sequence += 1
        timestamp = datetime.fromtimestamp(ts_ms / 1000, tz=UTC).strftime("%Y%m%dT%H%M%S%fZ")
        reason_slug = "_".join(reason.replace("-", "_") for reason in reasons)
        stem = f"{timestamp}_{self._sequence:06d}_{reason_slug}"
        png_path = self._config.root_dir / f"{stem}.png"
        json_path = self._config.root_dir / f"{stem}.json"

        if not cv2.imwrite(str(png_path), finder_roi):
            raise RuntimeError(f"Failed to write finder crop: {png_path}")

        json_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "created_at": datetime.now(tz=UTC).isoformat(),
                    "ts_ms": ts_ms,
                    "roi_name": self._roi_name,
                    "image_file": png_path.name,
                    "image_shape": list(finder_roi.shape),
                    "reasons": reasons,
                    "phase": phase,
                    "features": None if features is None else _features_to_json(features),
                    "signals": [_signal_to_json(signal) for signal in signals],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        logger.debug("finder_crop_recorded path=%s reasons=%s phase=%s", png_path, ",".join(reasons), phase)


def finder_recording_config_from_env(
    *,
    modes: str | None = None,
    root_dir: Path | None = None,
    interval_s: float | None = None,
    max_samples: int | None = None,
) -> FinderRecordingConfig:
    # Config sync is authoritative, but in development the child process also inherits
    # the parent environment. If an older/empty bridge config reaches the worker while
    # the explicit debug env flag is present, prefer that non-empty env value rather
    # than silently disabling recording.
    raw_modes = modes if modes is not None and modes.strip() else os.getenv("ZML_FINDER_RECORDING")
    parsed_modes = _parse_modes(raw_modes)
    default_max_samples = 500 if "accepted" in parsed_modes else 1
    config = FinderRecordingConfig(
        modes=parsed_modes,
        root_dir=root_dir
        or _env_path("ZML_FINDER_RECORDING_DIR")
        or default_finder_recording_dir(),
        interval_ms=_seconds_to_ms(
            interval_s
            if interval_s is not None
            else _env_float("ZML_FINDER_RECORDING_INTERVAL_S", default=60.0)
        ),
        max_samples=max_samples
        if max_samples is not None
        else _env_int("ZML_FINDER_RECORDING_MAX_SAMPLES", default=default_max_samples),
    )
    logger.info(
        "finder_recording_config_resolved modes=%s enabled=%s dir=%s max_samples=%s",
        ",".join(sorted(config.modes)) or "<off>",
        config.enabled,
        config.root_dir,
        config.max_samples,
    )
    return config


def _parse_modes(raw: str | None) -> frozenset[FinderRecordingMode]:
    if raw is None or raw.strip() == "":
        return frozenset()

    modes: set[FinderRecordingMode] = set()
    for item in raw.replace(";", ",").replace(" ", ",").split(","):
        normalized = item.strip().lower()
        if normalized in {"", "0", "false", "off", "none"}:
            continue
        if normalized == "all":
            modes.update(_VALID_MODES)
            continue
        if normalized in {"every", "timer", "every-n-seconds"}:
            normalized = "interval"
        if normalized in {"found", "detected", "located", "present"}:
            normalized = "accepted"
        if normalized == "manual":
            modes.add("manual")
        elif normalized == "interval":
            modes.add("interval")
        elif normalized == "accepted":
            modes.add("accepted")
        else:
            logger.warning("finder_recording_mode_ignored mode=%r", item)

    return frozenset(modes)


def _features_to_json(features: FinderFeatures) -> dict[str, object]:
    return {
        "status_kind": features.status_kind,
        "radar_signal_active": features.radar_signal_active,
        "modes_mask": features.modes_mask,
        "probes_per_drop": features.probes_per_drop,
        "ammo_per_drop": features.ammo_per_drop,
        "raw_status_text": features.raw_status_text,
        "raw_units_text": features.raw_units_text,
        "raw_details_text": features.raw_details_text,
        "hit_size_label": features.hit_size_label,
        "hit_size_index": features.hit_size_index,
        "resource_name": features.resource_name,
        "range_m": features.range_m,
        "depth_m": features.depth_m,
        "debug": dict(features.debug),
    }


def _signal_to_json(signal: MiningFinderSignal) -> dict[str, object]:
    return {
        "kind": signal.kind,
        "ts_ms": signal.ts_ms,
        "modes_mask": signal.modes_mask,
        "previous_modes_mask": signal.previous_modes_mask,
        "probes_per_drop": signal.probes_per_drop,
        "ammo_per_drop": signal.ammo_per_drop,
        "raw_text": signal.raw_text,
        "raw_details_text": signal.raw_details_text,
        "hit_size_label": signal.hit_size_label,
        "hit_size_index": signal.hit_size_index,
        "resource_name": signal.resource_name,
        "range_m": signal.range_m,
        "depth_m": signal.depth_m,
        "debug": dict(signal.debug),
    }


def default_finder_recording_dir() -> Path:
    return get_app_data_dir() / "ocr" / "finder-crops"


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
