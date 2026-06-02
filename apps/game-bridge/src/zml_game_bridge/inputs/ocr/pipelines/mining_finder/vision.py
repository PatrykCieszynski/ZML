from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal, Protocol

import cv2
import numpy as np

from zml_game_bridge.domain.mining import MiningMode
from zml_game_bridge.inputs.ocr.pipelines.image import (
    RelativeRect,
    crop_relative,
    to_bgr_u8,
    to_gray_u8,
    upscale,
)
from zml_game_bridge.inputs.ocr.pipelines.mining_finder.engine import (
    FinderTextEngine,
    TesserocrFinderTextEngine,
)
from zml_game_bridge.inputs.ocr.pipelines.mining_finder.model import FinderFeatures
from zml_game_bridge.inputs.ocr.pipelines.mining_finder.parsing import (
    classify_status,
    parse_details_text,
    parse_hit_size,
    parse_units_text,
)
from zml_game_bridge.inputs.ocr.pipelines.text import clean_ocr_text
from zml_game_bridge.inputs.ocr.profiling import OcrProfiler

logger = logging.getLogger(__name__)
ModeIconState = Literal["active", "inactive", "disabled"]


class FinderFeatureDetector(Protocol):
    def detect(self, finder_roi: np.ndarray) -> FinderFeatures: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class FinderPanelLayout:
    radar: RelativeRect = (0.02, 0.03, 0.48, 0.70)
    modes: RelativeRect = (0.02, 0.72, 0.48, 0.98)
    details: RelativeRect = (0.50, 0.03, 0.98, 0.35)
    units: RelativeRect = (0.50, 0.72, 0.98, 0.98)
    status: RelativeRect = (0.50, 0.36, 0.98, 0.70)


@dataclass(frozen=True, slots=True)
class VisionFinderFeatureConfig:
    radar_change_threshold: float = 0.015
    radar_center_threshold: float = 0.18
    mode_active_thresholds: tuple[float, float, float] = (0.31, 0.22, 0.40)
    mode_enabled_thresholds: tuple[float, float, float] = (0.18, 0.16, 0.08)
    text_ocr_scale: int = 3


@dataclass(frozen=True, slots=True)
class ModeIconDetection:
    state: ModeIconState
    active_score: float
    enabled_score: float
    disabled_score: float


class VisionFinderFeatureDetector:
    """
    Finder detector for visual state plus best-effort text OCR.

    The radar/ring animation is kept as debug signal only. Probe drops and
    preclaims come from the finder text state, because the blue rings also show
    search pulses and claim direction/range.
    """

    def __init__(
        self,
        *,
        layout: FinderPanelLayout | None = None,
        cfg: VisionFinderFeatureConfig | None = None,
        text_engine: FinderTextEngine | None = None,
        enable_text_ocr: bool = True,
        profiler: OcrProfiler | None = None,
    ) -> None:
        self._layout = layout or FinderPanelLayout()
        self._cfg = cfg or VisionFinderFeatureConfig()
        self._profiler = profiler
        self._previous_radar_blue_mask: np.ndarray | None = None
        self._text_engine = self._build_text_engine(text_engine, enable_text_ocr)

    def detect(self, finder_roi: np.ndarray) -> FinderFeatures:
        with self._measure("finder.detect"):
            with self._measure("finder.crop"):
                radar = crop_relative(finder_roi, self._layout.radar)
                modes = crop_relative(finder_roi, self._layout.modes)

            with self._measure("finder.visual"):
                radar_active, radar_score, radar_change_score, radar_center_score = (
                    self._detect_radar_signal(radar)
                )
                modes_mask, mode_detections = self._detect_modes(modes)
            text_features = self._detect_text_features(finder_roi)

            debug = {
                "radar_blue_score": radar_score,
                "radar_change_score": radar_change_score,
                "radar_center_blue_score": radar_center_score,
                **_mode_debug("ore", mode_detections[0]),
                **_mode_debug("enmatter", mode_detections[1]),
                **_mode_debug("treasure", mode_detections[2]),
            }
            return FinderFeatures(
                radar_signal_active=radar_active,
                modes_mask=modes_mask,
                status_kind=text_features.status_kind,
                raw_status_text=text_features.raw_status_text,
                probes_per_drop=text_features.probes_per_drop,
                ammo_per_drop=text_features.ammo_per_drop,
                raw_units_text=text_features.raw_units_text,
                raw_details_text=text_features.raw_details_text,
                hit_size_label=text_features.hit_size_label,
                hit_size_index=text_features.hit_size_index,
                resource_name=text_features.resource_name,
                range_m=text_features.range_m,
                depth_m=text_features.depth_m,
                debug=debug,
            )

    def close(self) -> None:
        self._previous_radar_blue_mask = None
        if self._text_engine is not None:
            self._text_engine.close()

    def _build_text_engine(
        self,
        text_engine: FinderTextEngine | None,
        enable_text_ocr: bool,
    ) -> FinderTextEngine | None:
        if text_engine is not None:
            return text_engine
        if not enable_text_ocr:
            return None
        try:
            return TesserocrFinderTextEngine()
        except RuntimeError:
            return None

    def _detect_radar_signal(self, radar_roi: np.ndarray) -> tuple[bool, float, float, float]:
        blue_mask = _blue_mask(radar_roi)
        previous = self._previous_radar_blue_mask
        self._previous_radar_blue_mask = blue_mask

        center_score = _center_score(blue_mask)
        change_score = 0.0
        if previous is None or previous.shape != blue_mask.shape:
            radar_score = center_score
            return (
                center_score >= self._cfg.radar_center_threshold,
                radar_score,
                change_score,
                center_score,
            )

        changed = np.count_nonzero(blue_mask != previous)
        change_score = float(changed) / float(blue_mask.size)
        radar_score = max(change_score, center_score)
        radar_active = (
            change_score >= self._cfg.radar_change_threshold
            or center_score >= self._cfg.radar_center_threshold
        )
        return radar_active, radar_score, change_score, center_score

    def _detect_text_features(self, finder_roi: np.ndarray) -> FinderFeatures:
        if self._text_engine is None:
            return FinderFeatures()

        try:
            raw_status = self._recognize_relative(finder_roi, self._layout.status)
            raw_units = self._recognize_relative(finder_roi, self._layout.units)
            raw_details = self._recognize_relative(finder_roi, self._layout.details)
        except Exception:
            logger.debug("Finder text OCR failed for frame", exc_info=True)
            return FinderFeatures()

        with self._measure("finder.parse"):
            probes_per_drop, ammo_per_drop = parse_units_text(raw_units)
            hit_size_label, hit_size_index = parse_hit_size(raw_status)
            range_m, depth_m, resource_name = parse_details_text(raw_details)

            return FinderFeatures(
                status_kind=classify_status(raw_status),
                raw_status_text=clean_ocr_text(raw_status),
                probes_per_drop=probes_per_drop,
                ammo_per_drop=ammo_per_drop,
                raw_units_text=clean_ocr_text(raw_units),
                raw_details_text=clean_ocr_text(raw_details),
                hit_size_label=hit_size_label,
                hit_size_index=hit_size_index,
                resource_name=resource_name,
                range_m=range_m,
                depth_m=depth_m,
            )

    def _recognize_relative(self, img: np.ndarray, rect: RelativeRect) -> str:
        if self._text_engine is None:
            return ""
        with self._measure("finder.crop"):
            roi = crop_relative(img, rect)
        with self._measure("finder.preprocess"):
            prepared = _prepare_text_ocr_image(roi, self._cfg.text_ocr_scale)
        with self._measure("finder.ocr"):
            return self._text_engine.recognize_text(prepared, psm=6)

    def _detect_modes(
        self,
        modes_roi: np.ndarray,
    ) -> tuple[int, tuple[ModeIconDetection, ModeIconDetection, ModeIconDetection]]:
        parts = np.array_split(modes_roi, 3, axis=1)
        detections = (
            _detect_mode_icon(
                parts[0],
                active_threshold=self._cfg.mode_active_thresholds[0],
                enabled_threshold=self._cfg.mode_enabled_thresholds[0],
            ),
            _detect_mode_icon(
                parts[1],
                active_threshold=self._cfg.mode_active_thresholds[1],
                enabled_threshold=self._cfg.mode_enabled_thresholds[1],
            ),
            _detect_mode_icon(
                parts[2],
                active_threshold=self._cfg.mode_active_thresholds[2],
                enabled_threshold=self._cfg.mode_enabled_thresholds[2],
            ),
        )

        mask = int(MiningMode.NONE)
        if detections[0].state == "active":
            mask |= int(MiningMode.ORE)
        if detections[1].state == "active":
            mask |= int(MiningMode.ENMATTER)
        if detections[2].state == "active":
            mask |= int(MiningMode.TREASURE)
        return mask, detections

    def _measure(self, name: str):
        if self._profiler is None:
            return _NullMeasure()
        return self._profiler.measure(name)


def _blue_mask(img: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(to_bgr_u8(img), cv2.COLOR_BGR2HSV)
    hue = hsv[:, :, 0]
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    return ((hue >= 85) & (hue <= 130) & (sat >= 70) & (val >= 60)).astype(np.uint8)


def _center_score(mask: np.ndarray) -> float:
    height, width = mask.shape
    x1, x2 = int(width * 0.32), int(width * 0.68)
    y1, y2 = int(height * 0.32), int(height * 0.68)
    center = mask[y1:y2, x1:x2]
    if center.size == 0:
        return 0.0
    return float(np.count_nonzero(center)) / float(center.size)


def _detect_mode_icon(
    img: np.ndarray,
    *,
    active_threshold: float,
    enabled_threshold: float,
) -> ModeIconDetection:
    hsv = cv2.cvtColor(to_bgr_u8(img), cv2.COLOR_BGR2HSV)
    hue = hsv[:, :, 0]
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    enabled = (hue >= 40) & (hue <= 95) & (sat >= 35) & (val >= 55)
    active = enabled & (val >= 110)
    disabled = (sat <= 45) & (val >= 45)
    enabled_score = _mask_score(enabled)
    active_score = _mask_score(active)
    disabled_score = _mask_score(disabled)
    if active_score >= active_threshold:
        state: ModeIconState = "active"
    elif enabled_score >= enabled_threshold:
        state = "inactive"
    else:
        state = "disabled"
    return ModeIconDetection(
        state=state,
        active_score=active_score,
        enabled_score=enabled_score,
        disabled_score=disabled_score,
    )


def _mask_score(mask: np.ndarray) -> float:
    if mask.size == 0:
        return 0.0
    return float(np.count_nonzero(mask)) / float(mask.size)


def _mode_debug(prefix: str, detection: ModeIconDetection) -> dict[str, float]:
    state_code = {"disabled": 0.0, "inactive": 1.0, "active": 2.0}[detection.state]
    return {
        f"mode_{prefix}_score": detection.active_score,
        f"mode_{prefix}_active_score": detection.active_score,
        f"mode_{prefix}_enabled_score": detection.enabled_score,
        f"mode_{prefix}_disabled_score": detection.disabled_score,
        f"mode_{prefix}_state": state_code,
    }


def _prepare_text_ocr_image(img: np.ndarray, scale: int) -> np.ndarray:
    return upscale(to_gray_u8(img), scale, cv2.INTER_CUBIC)


class _NullMeasure:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *args: object) -> None:
        return None
