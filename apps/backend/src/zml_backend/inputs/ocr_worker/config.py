from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from zml_ocr_protocol.messages import (
    ApplyConfigPayload,
    FinderPanelPayload,
    FinderRecordingConfigPayload,
    FinderRecordingMode,
    FinderRuntimeConfig,
    OcrConfigSnapshot,
    OcrRoiProfilePayload,
    PixelRectPayload,
    PositionRoisPayload,
    PositionRuntimeConfig,
    PositionSnapshotRecordingConfigPayload,
    ProfilingConfig,
    RelativeRectPayload,
    ScreenRoiPayload,
    ScreenRoisPayload,
)

from zml_backend.settings import Settings

logger = logging.getLogger(__name__)

_INITIAL_CONFIG_REVISION = 1


def build_desired_ocr_config(settings: Settings) -> ApplyConfigPayload:
    return ApplyConfigPayload(
        revision=_INITIAL_CONFIG_REVISION,
        config=OcrConfigSnapshot(
            capture_hz=settings.ocr_capture_hz,
            capture_artifacts_dir=str(settings.ocr_capture_artifacts_dir),
            roi_profile=load_ocr_roi_profile_payload(settings.ocr_profile_path),
            finder=FinderRuntimeConfig(
                presence_check_enabled=settings.finder_presence_check_enabled,
                debug_logging=settings.finder_debug_logging,
                recording=FinderRecordingConfigPayload(
                    modes=_parse_finder_recording_modes(settings.finder_recording_modes),
                    directory=str(settings.finder_recording_dir),
                    interval_ms=_seconds_to_ms(settings.finder_recording_interval_s),
                    max_samples=max(0, settings.finder_recording_max_samples),
                ),
            ),
            position=PositionRuntimeConfig(
                snapshot_recording=PositionSnapshotRecordingConfigPayload(
                    enabled=settings.position_roi_snapshot_enabled,
                    directory=str(settings.position_roi_snapshot_dir),
                    interval_ms=_seconds_to_ms(settings.position_roi_snapshot_interval_s),
                    max_samples=max(0, settings.position_roi_snapshot_max_samples),
                )
            ),
            profiling=ProfilingConfig(
                enabled=settings.ocr_profiling_enabled,
                interval_ms=_seconds_to_ms(settings.ocr_profiling_interval_s),
            ),
        ),
    )


def load_ocr_roi_profile_payload(path: Path) -> OcrRoiProfilePayload:
    fallback = default_ocr_roi_profile_payload()
    if not path.exists():
        _try_write_default_profile(path, fallback)
        return fallback

    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
        normalized = _normalize_profile_json(raw)
        normalized = _migrate_legacy_finder_panel_defaults(normalized)
        fallback_payload = cast(dict[str, object], fallback.model_dump(mode="python"))
        merged = _deep_merge(fallback_payload, normalized)
        return OcrRoiProfilePayload.model_validate(merged)
    except Exception:
        logger.exception("ocr_desired_profile_load_failed path=%s", path)
        return fallback


def default_ocr_roi_profile_payload() -> OcrRoiProfilePayload:
    return OcrRoiProfilePayload(
        schema_version=1,
        name="mvp-default",
        screen_rois=ScreenRoisPayload(
            compass=ScreenRoiPayload(
                name="compass_mvp_absolute",
                anchor="top_left",
                x=2190,
                y=965,
                width=361,
                height=446,
                enabled=True,
            ),
            finder=ScreenRoiPayload(
                name="finder_mvp_bottom_left",
                anchor="bottom_left",
                x=3,
                y=3,
                width=347,
                height=239,
                enabled=True,
            ),
            deeds=ScreenRoiPayload(
                name="deeds_mvp_left_panel",
                anchor="top_left",
                x=20,
                y=260,
                width=680,
                height=260,
                enabled=True,
            ),
            loot=None,
        ),
        position_rois=PositionRoisPayload(
            planet=PixelRectPayload(x1=23, x2=362, y1=0, y2=30),
            lon=PixelRectPayload(x1=85, x2=145, y1=350, y2=370),
            lat=PixelRectPayload(x1=90, x2=145, y1=375, y2=395),
        ),
        finder_panel=FinderPanelPayload(
            radar=RelativeRectPayload(x1=0.02, y1=0.03, x2=0.464, y2=0.70),
            modes=RelativeRectPayload(x1=0.02, y1=0.72, x2=0.464, y2=0.98),
            details=RelativeRectPayload(x1=0.484, y1=0.03, x2=1.0, y2=0.35),
            units=RelativeRectPayload(x1=0.484, y1=0.72, x2=1.0, y2=0.98),
            status=RelativeRectPayload(x1=0.484, y1=0.36, x2=1.0, y2=0.70),
        ),
    )


def _normalize_profile_json(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("OCR ROI profile must be a JSON object")
    raw = cast(Mapping[object, object], value)
    normalized: dict[str, object] = {}
    for key, item in raw.items():
        if not isinstance(key, str):
            raise ValueError("OCR ROI profile keys must be strings")
        normalized[key] = item
    normalized["schema_version"] = normalized.pop("version", normalized.get("schema_version", 1))
    finder_panel = normalized.get("finder_panel")
    if isinstance(finder_panel, Mapping):
        panel = cast(Mapping[object, object], finder_panel)
        normalized_panel: dict[str, object] = {}
        for key, item in panel.items():
            if not isinstance(key, str):
                raise ValueError("finder panel keys must be strings")
            normalized_panel[key] = _normalize_relative_rect(item)
        normalized["finder_panel"] = normalized_panel
    return normalized


def _migrate_legacy_finder_panel_defaults(profile: dict[str, object]) -> dict[str, object]:
    raw_panel = profile.get("finder_panel")
    if not isinstance(raw_panel, Mapping):
        return profile

    panel = cast(Mapping[str, object], raw_panel)
    replacements: dict[str, tuple[dict[str, float], dict[str, float]]] = {
        "radar": (
            {"x1": 0.02, "y1": 0.03, "x2": 0.48, "y2": 0.70},
            {"x1": 0.02, "y1": 0.03, "x2": 0.464, "y2": 0.70},
        ),
        "modes": (
            {"x1": 0.02, "y1": 0.72, "x2": 0.48, "y2": 0.98},
            {"x1": 0.02, "y1": 0.72, "x2": 0.464, "y2": 0.98},
        ),
        "details": (
            {"x1": 0.50, "y1": 0.03, "x2": 0.98, "y2": 0.35},
            {"x1": 0.484, "y1": 0.03, "x2": 1.0, "y2": 0.35},
        ),
        "units": (
            {"x1": 0.50, "y1": 0.72, "x2": 0.98, "y2": 0.98},
            {"x1": 0.484, "y1": 0.72, "x2": 1.0, "y2": 0.98},
        ),
        "status": (
            {"x1": 0.50, "y1": 0.36, "x2": 0.98, "y2": 0.70},
            {"x1": 0.484, "y1": 0.36, "x2": 1.0, "y2": 0.70},
        ),
    }
    migrated_panel = dict(panel)
    changed = False
    for key, (legacy, replacement) in replacements.items():
        if migrated_panel.get(key) == legacy:
            migrated_panel[key] = replacement
            changed = True
    if not changed:
        return profile

    migrated = dict(profile)
    migrated["finder_panel"] = migrated_panel
    return migrated


def _normalize_relative_rect(value: object) -> object:
    if isinstance(value, list | tuple):
        items = cast(Sequence[object], value)
        if len(items) == 4:
            return {"x1": items[0], "y1": items[1], "x2": items[2], "y2": items[3]}
    return cast(object, value)


def _deep_merge(
    base: dict[str, object],
    override: Mapping[str, object],
) -> dict[str, object]:
    merged = dict(base)
    for key, value in override.items():
        previous = merged.get(key)
        if isinstance(previous, dict) and isinstance(value, Mapping):
            merged[key] = _deep_merge(
                cast(dict[str, object], previous),
                cast(Mapping[str, object], value),
            )
        else:
            merged[key] = value
    return merged


def _parse_finder_recording_modes(raw: str) -> list[FinderRecordingMode]:
    modes: set[FinderRecordingMode] = set()
    for item in raw.replace(";", ",").replace(" ", ",").split(","):
        normalized = item.strip().lower()
        if normalized in {"", "0", "false", "off", "none"}:
            continue
        if normalized == "all":
            modes.update({"accepted", "manual", "interval"})
        elif normalized == "manual":
            modes.add("manual")
        elif normalized in {"interval", "every", "timer", "every-n-seconds"}:
            modes.add("interval")
        elif normalized in {"accepted", "found", "detected", "located", "present"}:
            modes.add("accepted")
        else:
            logger.warning("finder_recording_mode_ignored mode=%r", item)
    return sorted(modes)


def _try_write_default_profile(path: Path, profile: OcrRoiProfilePayload) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(profile.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError:
        logger.warning("ocr_desired_profile_default_write_failed path=%s", path, exc_info=True)


def _seconds_to_ms(value: float) -> int:
    return max(1, int(value * 1_000))