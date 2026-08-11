from __future__ import annotations

import re
from dataclasses import dataclass

import cv2
import numpy as np

from zml_ocr_worker.calibration.model import LocatedCompass
from zml_ocr_worker.pipelines.mining_finder.engine import FinderTextEngine

_COORDINATE_VALUE_RE = re.compile(r"\b(\d{4,7}|unknown)\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class CompassCoordinateRead:
    longitude: int | None
    latitude: int | None
    longitude_unknown: bool
    latitude_unknown: bool
    raw_text: str

    @property
    def has_position(self) -> bool:
        return self.longitude is not None and self.latitude is not None


@dataclass(frozen=True, slots=True)
class CompassCoordinateReaderConfig:
    left_radius: float = -1.48
    longitude_top_radius: float = 0.94
    longitude_bottom_radius: float = 1.14
    latitude_top_radius: float = 1.10
    latitude_bottom_radius: float = 1.32
    right_radius_candidates: tuple[float, ...] = (-0.50, -0.28, -0.04, 0.16)
    upscale_factors: tuple[int, ...] = (3, 4)
    page_seg_modes: tuple[int, ...] = (7, 11)


class CompassCoordinateReader:
    """Read fixed Lon/Lat lines derived from a located Compass radar."""

    def __init__(
        self,
        *,
        text_engine: FinderTextEngine,
        config: CompassCoordinateReaderConfig | None = None,
    ) -> None:
        self._text_engine = text_engine
        self._config = config or CompassCoordinateReaderConfig()

    def read(self, frame: np.ndarray, compass: LocatedCompass) -> CompassCoordinateRead:
        longitude, longitude_unknown, longitude_text = self._read_line(
            frame,
            compass,
            label="lon",
            top_radius=self._config.longitude_top_radius,
            bottom_radius=self._config.longitude_bottom_radius,
        )
        latitude, latitude_unknown, latitude_text = self._read_line(
            frame,
            compass,
            label="lat",
            top_radius=self._config.latitude_top_radius,
            bottom_radius=self._config.latitude_bottom_radius,
        )
        raw_parts = [part for part in (longitude_text, latitude_text) if part]
        return CompassCoordinateRead(
            longitude=longitude,
            latitude=latitude,
            longitude_unknown=longitude_unknown,
            latitude_unknown=latitude_unknown,
            raw_text="\n---\n".join(raw_parts),
        )

    def _read_line(
        self,
        frame: np.ndarray,
        compass: LocatedCompass,
        *,
        label: str,
        top_radius: float,
        bottom_radius: float,
    ) -> tuple[int | None, bool, str]:
        attempts: list[str] = []
        for right_radius in self._config.right_radius_candidates:
            line = _crop_coordinate_line(
                frame,
                compass,
                left_radius=self._config.left_radius,
                right_radius=right_radius,
                top_radius=top_radius,
                bottom_radius=bottom_radius,
            )
            for scale in self._config.upscale_factors:
                prepared = _upscale(line, scale=scale)
                for psm in self._config.page_seg_modes:
                    text = self._text_engine.recognize_text(prepared, psm=psm)
                    stripped = text.strip()
                    if stripped:
                        attempts.append(stripped)
                    value, unknown = _parse_labeled_value(text, label)
                    if value is not None or unknown:
                        return value, unknown, "\n".join(attempts)
        return None, False, "\n".join(attempts)


def _crop_coordinate_line(
    frame: np.ndarray,
    compass: LocatedCompass,
    *,
    left_radius: float,
    right_radius: float,
    top_radius: float,
    bottom_radius: float,
) -> np.ndarray:
    return _crop_from_radar(
        frame,
        compass,
        left_radius=left_radius,
        right_radius=right_radius,
        top_radius=top_radius,
        bottom_radius=bottom_radius,
    )


def _crop_from_radar(
    frame: np.ndarray,
    compass: LocatedCompass,
    *,
    left_radius: float,
    right_radius: float,
    top_radius: float,
    bottom_radius: float,
) -> np.ndarray:
    height = int(frame.shape[0])
    width = int(frame.shape[1])
    radius = compass.radius
    x1 = max(0, min(width, round(compass.center_x + radius * left_radius)))
    x2 = max(0, min(width, round(compass.center_x + radius * right_radius)))
    y1 = max(0, min(height, round(compass.center_y + radius * top_radius)))
    y2 = max(0, min(height, round(compass.center_y + radius * bottom_radius)))
    if x2 <= x1 or y2 <= y1:
        return np.zeros((1, 1, 3), dtype=np.uint8)
    return np.ascontiguousarray(frame[y1:y2, x1:x2])


def _upscale(image: np.ndarray, *, scale: int) -> np.ndarray:
    if image.size == 0 or scale <= 1:
        return image
    return cv2.resize(
        image,
        None,
        fx=float(scale),
        fy=float(scale),
        interpolation=cv2.INTER_CUBIC,
    )


def _parse_labeled_value(text: str, label: str) -> tuple[int | None, bool]:
    for line in text.splitlines():
        normalized = " ".join(line.lower().replace(";", ":").split())
        if label not in normalized:
            continue
        label_index = normalized.find(label)
        match = _COORDINATE_VALUE_RE.search(normalized[label_index + len(label) :])
        if match is None:
            continue
        value = match.group(1).lower()
        if value == "unknown":
            return None, True
        try:
            return int(value), False
        except ValueError:
            continue
    return None, False
