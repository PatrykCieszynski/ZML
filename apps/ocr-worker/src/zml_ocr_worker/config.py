from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
from zml_ocr_protocol.messages import (
    ApplyConfigPayload,
    OcrRoiProfilePayload,
    PixelRectPayload,
    RelativeRectPayload,
    ScreenRoiPayload,
)

from zml_ocr_worker.capture.model import RoiRect
from zml_ocr_worker.pipelines.image import RelativeRect
from zml_ocr_worker.pipelines.mining_finder.vision import FinderPanelLayout
from zml_ocr_worker.pipelines.position.model import PositionRois

logger = logging.getLogger(__name__)

ScreenRoiAnchor = Literal["top_left", "bottom_left"]
JsonObject = Mapping[str, object]


@dataclass(frozen=True, slots=True)
class ScreenRoiConfig:
    name: str
    anchor: ScreenRoiAnchor
    x: int
    y: int
    width: int
    height: int
    enabled: bool = True

    def crop(self, frame: np.ndarray) -> np.ndarray | None:
        if not self.enabled:
            return None
        return self.to_rect(frame).crop(frame)

    def to_rect(self, frame: np.ndarray) -> RoiRect:
        frame_height = int(frame.shape[0])
        if self.anchor == "top_left":
            x1 = self.x
            y1 = self.y
        elif self.anchor == "bottom_left":
            x1 = self.x
            y1 = frame_height - self.y - self.height
        else:
            raise ValueError(f"Unsupported ROI anchor: {self.anchor}")

        return RoiRect(
            x1=x1,
            x2=x1 + self.width,
            y1=y1,
            y2=y1 + self.height,
        )


@dataclass(frozen=True, slots=True)
class PositionRoiConfig:
    planet: RoiRect
    lon: RoiRect
    lat: RoiRect

    def to_position_rois(self) -> PositionRois:
        return PositionRois(
            planet=self.planet,
            lon=self.lon,
            lat=self.lat,
        )


@dataclass(frozen=True, slots=True)
class FinderPanelLayoutConfig:
    radar: RelativeRect
    modes: RelativeRect
    details: RelativeRect
    units: RelativeRect
    status: RelativeRect

    def to_panel_layout(self) -> FinderPanelLayout:
        return FinderPanelLayout(
            radar=self.radar,
            modes=self.modes,
            details=self.details,
            units=self.units,
            status=self.status,
        )


@dataclass(frozen=True, slots=True)
class OcrScreenRois:
    compass: ScreenRoiConfig
    finder: ScreenRoiConfig
    deeds: ScreenRoiConfig
    loot: ScreenRoiConfig | None = None


@dataclass(frozen=True, slots=True)
class OcrRoiProfile:
    name: str
    screen_rois: OcrScreenRois
    position_rois: PositionRoiConfig
    finder_panel: FinderPanelLayoutConfig


@dataclass(frozen=True, slots=True)
class AppliedOcrConfig:
    revision: int
    capture_hz: float
    capture_artifacts_dir: Path
    roi_profile: OcrRoiProfile
    finder_debug_logging: bool
    finder_recording_modes: str
    finder_recording_dir: Path
    finder_recording_interval_s: float
    finder_recording_max_samples: int
    finder_presence_check_enabled: bool
    position_roi_snapshot_enabled: bool
    position_roi_snapshot_dir: Path
    position_roi_snapshot_interval_s: float
    position_roi_snapshot_max_samples: int
    ocr_profiling_enabled: bool
    ocr_profiling_interval_s: float


def applied_ocr_config(payload: ApplyConfigPayload) -> AppliedOcrConfig:
    config = payload.config
    return AppliedOcrConfig(
        revision=payload.revision,
        capture_hz=config.capture_hz,
        capture_artifacts_dir=Path(config.capture_artifacts_dir),
        roi_profile=_profile_from_protocol(config.roi_profile),
        finder_debug_logging=config.finder.debug_logging,
        finder_recording_modes=",".join(config.finder.recording.modes),
        finder_recording_dir=Path(config.finder.recording.directory),
        finder_recording_interval_s=_milliseconds_to_seconds(config.finder.recording.interval_ms),
        finder_recording_max_samples=config.finder.recording.max_samples,
        finder_presence_check_enabled=config.finder.presence_check_enabled,
        position_roi_snapshot_enabled=config.position.snapshot_recording.enabled,
        position_roi_snapshot_dir=Path(config.position.snapshot_recording.directory),
        position_roi_snapshot_interval_s=_milliseconds_to_seconds(
            config.position.snapshot_recording.interval_ms
        ),
        position_roi_snapshot_max_samples=config.position.snapshot_recording.max_samples,
        ocr_profiling_enabled=config.profiling.enabled,
        ocr_profiling_interval_s=_milliseconds_to_seconds(config.profiling.interval_ms),
    )


def _profile_from_protocol(payload: OcrRoiProfilePayload) -> OcrRoiProfile:
    return OcrRoiProfile(
        name=payload.name,
        screen_rois=OcrScreenRois(
            compass=_screen_roi_from_protocol(payload.screen_rois.compass),
            finder=_screen_roi_from_protocol(payload.screen_rois.finder),
            deeds=_screen_roi_from_protocol(payload.screen_rois.deeds),
            loot=(
                None
                if payload.screen_rois.loot is None
                else _screen_roi_from_protocol(payload.screen_rois.loot)
            ),
        ),
        position_rois=PositionRoiConfig(
            planet=_pixel_rect_from_protocol(payload.position_rois.planet),
            lon=_pixel_rect_from_protocol(payload.position_rois.lon),
            lat=_pixel_rect_from_protocol(payload.position_rois.lat),
        ),
        finder_panel=FinderPanelLayoutConfig(
            radar=_relative_rect_from_protocol(payload.finder_panel.radar),
            modes=_relative_rect_from_protocol(payload.finder_panel.modes),
            details=_relative_rect_from_protocol(payload.finder_panel.details),
            units=_relative_rect_from_protocol(payload.finder_panel.units),
            status=_relative_rect_from_protocol(payload.finder_panel.status),
        ),
    )


def _screen_roi_from_protocol(payload: ScreenRoiPayload) -> ScreenRoiConfig:
    return ScreenRoiConfig(
        name=payload.name,
        anchor=payload.anchor,
        x=payload.x,
        y=payload.y,
        width=payload.width,
        height=payload.height,
        enabled=payload.enabled,
    )


def _pixel_rect_from_protocol(payload: PixelRectPayload) -> RoiRect:
    return RoiRect(x1=payload.x1, x2=payload.x2, y1=payload.y1, y2=payload.y2)


def _relative_rect_from_protocol(payload: RelativeRectPayload) -> RelativeRect:
    return payload.x1, payload.y1, payload.x2, payload.y2


def _milliseconds_to_seconds(value: int) -> float:
    return value / 1_000.0


def load_ocr_roi_profile(path: Path | None) -> OcrRoiProfile:
    default_profile = default_ocr_roi_profile()

    if path is None:
        return default_profile

    if not path.exists():
        _try_write_default_profile(path, default_profile)
        return default_profile

    try:
        payload: object = json.loads(path.read_text(encoding="utf-8"))
        return _profile_from_payload(payload, fallback=default_profile)
    except Exception:
        logger.exception("ocr_roi_profile_load_failed path=%s", path)
        return default_profile


def default_ocr_roi_profile() -> OcrRoiProfile:
    return OcrRoiProfile(
        name="mvp-default",
        screen_rois=OcrScreenRois(
            compass=ScreenRoiConfig(
                name="compass_mvp_absolute",
                anchor="top_left",
                x=2190,
                y=965,
                width=361,
                height=446,
            ),
            finder=ScreenRoiConfig(
                name="finder_mvp_bottom_left",
                anchor="bottom_left",
                x=3,
                y=3,
                width=347,
                height=239,
            ),
            deeds=ScreenRoiConfig(
                name="deeds_mvp_left_panel",
                anchor="top_left",
                x=20,
                y=260,
                width=680,
                height=260,
            ),
            loot=None,
        ),
        position_rois=PositionRoiConfig(
            planet=RoiRect(x1=23, x2=362, y1=0, y2=30),
            lon=RoiRect(x1=85, x2=145, y1=350, y2=370),
            lat=RoiRect(x1=90, x2=145, y1=375, y2=395),
        ),
        finder_panel=FinderPanelLayoutConfig(
            radar=(0.02, 0.03, 0.464, 0.70),
            modes=(0.02, 0.72, 0.464, 0.98),
            details=(0.484, 0.03, 1.0, 0.35),
            units=(0.484, 0.72, 1.0, 0.98),
            status=(0.484, 0.36, 1.0, 0.70),
        ),
    )


def _try_write_default_profile(path: Path, profile: OcrRoiProfile) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(_profile_to_json(profile), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError:
        logger.warning("ocr_roi_profile_default_write_failed path=%s", path, exc_info=True)


def _profile_from_payload(payload: object, *, fallback: OcrRoiProfile) -> OcrRoiProfile:
    raw = _json_object(payload)
    if raw is None:
        raise ValueError("OCR ROI profile must be a JSON object")

    return OcrRoiProfile(
        name=_optional_str(raw.get("name")) or fallback.name,
        screen_rois=_screen_rois_from_json(
            raw.get("screen_rois"),
            fallback=fallback.screen_rois,
        ),
        position_rois=_position_rois_from_json(
            raw.get("position_rois"),
            fallback=fallback.position_rois,
        ),
        finder_panel=_finder_panel_from_json(
            raw.get("finder_panel"),
            fallback=fallback.finder_panel,
        ),
    )


def _screen_rois_from_json(value: object, *, fallback: OcrScreenRois) -> OcrScreenRois:
    raw = _json_object(value)
    if raw is None:
        return fallback

    return OcrScreenRois(
        compass=_screen_roi_from_json(raw.get("compass"), fallback=fallback.compass),
        finder=_screen_roi_from_json(raw.get("finder"), fallback=fallback.finder),
        deeds=_screen_roi_from_json(raw.get("deeds"), fallback=fallback.deeds),
        loot=_optional_screen_roi_from_json(raw.get("loot"), fallback=fallback.loot),
    )


def _screen_roi_from_json(value: object, *, fallback: ScreenRoiConfig) -> ScreenRoiConfig:
    raw = _json_object(value)
    if raw is None:
        return fallback

    return ScreenRoiConfig(
        name=_optional_str(raw.get("name")) or fallback.name,
        anchor=_screen_anchor(raw.get("anchor"), fallback=fallback.anchor),
        x=_int(raw.get("x"), fallback=fallback.x),
        y=_int(raw.get("y"), fallback=fallback.y),
        width=_positive_int(raw.get("width"), fallback=fallback.width),
        height=_positive_int(raw.get("height"), fallback=fallback.height),
        enabled=_bool(raw.get("enabled"), fallback=fallback.enabled),
    )


def _optional_screen_roi_from_json(
    value: object,
    *,
    fallback: ScreenRoiConfig | None,
) -> ScreenRoiConfig | None:
    if value is None:
        return fallback

    fallback_value = fallback or ScreenRoiConfig(
        name="loot_custom",
        anchor="top_left",
        x=0,
        y=0,
        width=1,
        height=1,
        enabled=False,
    )
    return _screen_roi_from_json(value, fallback=fallback_value)


def _position_rois_from_json(value: object, *, fallback: PositionRoiConfig) -> PositionRoiConfig:
    raw = _json_object(value)
    if raw is None:
        return fallback

    return PositionRoiConfig(
        planet=_roi_rect_from_json(raw.get("planet"), fallback=fallback.planet),
        lon=_roi_rect_from_json(raw.get("lon"), fallback=fallback.lon),
        lat=_roi_rect_from_json(raw.get("lat"), fallback=fallback.lat),
    )


def _finder_panel_from_json(
    value: object,
    *,
    fallback: FinderPanelLayoutConfig,
) -> FinderPanelLayoutConfig:
    raw = _json_object(value)
    if raw is None:
        return fallback

    radar = _relative_rect_from_json(raw.get("radar"), fallback=fallback.radar)
    modes = _relative_rect_from_json(raw.get("modes"), fallback=fallback.modes)
    details = _relative_rect_from_json(raw.get("details"), fallback=fallback.details)
    units = _relative_rect_from_json(raw.get("units"), fallback=fallback.units)
    status = _relative_rect_from_json(raw.get("status"), fallback=fallback.status)
    return FinderPanelLayoutConfig(
        radar=_migrate_legacy_finder_rect(
            radar,
            legacy=(0.02, 0.03, 0.48, 0.70),
            replacement=fallback.radar,
        ),
        modes=_migrate_legacy_finder_rect(
            modes,
            legacy=(0.02, 0.72, 0.48, 0.98),
            replacement=fallback.modes,
        ),
        details=_migrate_legacy_finder_rect(
            details,
            legacy=(0.50, 0.03, 0.98, 0.35),
            replacement=fallback.details,
        ),
        units=_migrate_legacy_finder_rect(
            units,
            legacy=(0.50, 0.72, 0.98, 0.98),
            replacement=fallback.units,
        ),
        status=_migrate_legacy_finder_rect(
            status,
            legacy=(0.50, 0.36, 0.98, 0.70),
            replacement=fallback.status,
        ),
    )


def _roi_rect_from_json(value: object, *, fallback: RoiRect) -> RoiRect:
    raw = _json_object(value)
    if raw is None:
        return fallback

    return RoiRect(
        x1=_int(raw.get("x1"), fallback=fallback.x1),
        x2=_int(raw.get("x2"), fallback=fallback.x2),
        y1=_int(raw.get("y1"), fallback=fallback.y1),
        y2=_int(raw.get("y2"), fallback=fallback.y2),
    )


def _relative_rect_from_json(value: object, *, fallback: RelativeRect) -> RelativeRect:
    items = _json_sequence(value)
    if items is None or len(items) != 4:
        return fallback

    values: list[float] = []
    for item in items:
        if isinstance(item, bool) or not isinstance(item, int | float):
            return fallback
        values.append(max(0.0, min(1.0, float(item))))

    return values[0], values[1], values[2], values[3]


def _migrate_legacy_finder_rect(
    value: RelativeRect,
    *,
    legacy: RelativeRect,
    replacement: RelativeRect,
) -> RelativeRect:
    return replacement if value == legacy else value


def _profile_to_json(profile: OcrRoiProfile) -> dict[str, object]:
    return {
        "version": 1,
        "name": profile.name,
        "screen_rois": {
            "compass": _screen_roi_to_json(profile.screen_rois.compass),
            "finder": _screen_roi_to_json(profile.screen_rois.finder),
            "deeds": _screen_roi_to_json(profile.screen_rois.deeds),
            "loot": (
                None
                if profile.screen_rois.loot is None
                else _screen_roi_to_json(profile.screen_rois.loot)
            ),
        },
        "position_rois": {
            "planet": _roi_rect_to_json(profile.position_rois.planet),
            "lon": _roi_rect_to_json(profile.position_rois.lon),
            "lat": _roi_rect_to_json(profile.position_rois.lat),
        },
        "finder_panel": {
            "radar": list(profile.finder_panel.radar),
            "modes": list(profile.finder_panel.modes),
            "details": list(profile.finder_panel.details),
            "units": list(profile.finder_panel.units),
            "status": list(profile.finder_panel.status),
        },
    }


def _screen_roi_to_json(roi: ScreenRoiConfig) -> dict[str, object]:
    return {
        "name": roi.name,
        "anchor": roi.anchor,
        "x": roi.x,
        "y": roi.y,
        "width": roi.width,
        "height": roi.height,
        "enabled": roi.enabled,
    }


def _roi_rect_to_json(roi: RoiRect) -> dict[str, int]:
    return {
        "x1": roi.x1,
        "x2": roi.x2,
        "y1": roi.y1,
        "y2": roi.y2,
    }


def _json_object(value: object) -> JsonObject | None:
    if not isinstance(value, Mapping):
        return None

    raw = value
    parsed: dict[str, object] = {}

    for key, item in raw.items():
        if not isinstance(key, str):
            return None
        parsed[key] = item

    return parsed


def _json_sequence(value: object) -> Sequence[object] | None:
    if isinstance(value, str | bytes | bytearray):
        return None
    if not isinstance(value, Sequence):
        return None
    return value


def _screen_anchor(value: object, *, fallback: ScreenRoiAnchor) -> ScreenRoiAnchor:
    if value == "top_left":
        return "top_left"
    if value == "bottom_left":
        return "bottom_left"
    return fallback


def _optional_str(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _bool(value: object, *, fallback: bool) -> bool:
    return value if isinstance(value, bool) else fallback


def _int(value: object, *, fallback: int) -> int:
    if isinstance(value, bool):
        return fallback
    return value if isinstance(value, int) else fallback


def _positive_int(value: object, *, fallback: int) -> int:
    parsed = _int(value, fallback=fallback)
    return parsed if parsed > 0 else fallback