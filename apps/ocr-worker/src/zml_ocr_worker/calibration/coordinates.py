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


class CompassCoordinateReader:
    """Read Lon/Lat from the local text area below a located Compass radar."""

    def __init__(self, *, text_engine: FinderTextEngine) -> None:
        self._text_engine = text_engine

    def read(self, frame: np.ndarray, compass: LocatedCompass) -> CompassCoordinateRead:
        broad = _crop_coordinate_region(frame, compass)
        broad_text = self._recognize_upscaled(broad, scale=2, psm=6)
        longitude, longitude_unknown = _parse_labeled_value(broad_text, "lon")
        latitude, latitude_unknown = _parse_labeled_value(broad_text, "lat")

        fallback_texts: list[str] = []
        if longitude is None and not longitude_unknown:
            lon_line = _crop_coordinate_line(frame, compass, start_radius=0.94, end_radius=1.14)
            lon_text = self._recognize_upscaled(lon_line, scale=3, psm=11)
            fallback_texts.append(lon_text)
            longitude, longitude_unknown = _parse_labeled_value(lon_text, "lon")

        if latitude is None and not latitude_unknown:
            lat_line = _crop_coordinate_line(frame, compass, start_radius=1.10, end_radius=1.34)
            lat_text = self._recognize_upscaled(lat_line, scale=3, psm=11)
            fallback_texts.append(lat_text)
            latitude, latitude_unknown = _parse_labeled_value(lat_text, "lat")

        raw_parts = [part.strip() for part in [broad_text, *fallback_texts] if part.strip()]
        return CompassCoordinateRead(
            longitude=longitude,
            latitude=latitude,
            longitude_unknown=longitude_unknown,
            latitude_unknown=latitude_unknown,
            raw_text="\n---\n".join(raw_parts),
        )

    def _recognize_upscaled(self, image: np.ndarray, *, scale: int, psm: int) -> str:
        if image.size == 0:
            return ""
        if scale > 1:
            image = cv2.resize(
                image,
                None,
                fx=float(scale),
                fy=float(scale),
                interpolation=cv2.INTER_CUBIC,
            )
        return self._text_engine.recognize_text(image, psm=psm)


def _crop_coordinate_region(frame: np.ndarray, compass: LocatedCompass) -> np.ndarray:
    return _crop_from_radar(
        frame,
        compass,
        left_radius=-1.45,
        right_radius=0.15,
        top_radius=0.82,
        bottom_radius=1.52,
    )


def _crop_coordinate_line(
    frame: np.ndarray,
    compass: LocatedCompass,
    *,
    start_radius: float,
    end_radius: float,
) -> np.ndarray:
    return _crop_from_radar(
        frame,
        compass,
        left_radius=-1.50,
        right_radius=-0.08,
        top_radius=start_radius,
        bottom_radius=end_radius,
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
