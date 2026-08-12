from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from zml_ocr_worker.calibration.model import LocatedCompass, LocatedRegion
from zml_ocr_worker.capture.model import RoiRect
from zml_ocr_worker.pipelines.image import RelativeRect
from zml_ocr_worker.pipelines.mining_finder.vision import FinderPanelLayout
from zml_ocr_worker.pipelines.position.model import CoordinateRois


@dataclass(frozen=True, slots=True)
class CalibrationUiDiagnosticsConfig:
    root_dir: Path
    interval_ms: int = 750
    context_padding_px: int = 24


class CalibrationUiDiagnosticsRecorder:
    def __init__(self, *, config: CalibrationUiDiagnosticsConfig) -> None:
        self._config = config
        self._last_finder_ts_ms = 0
        self._last_compass_ts_ms = 0

    def clear(self) -> None:
        for region in ("finder", "compass"):
            for suffix in ("png", "json"):
                path = self._config.root_dir / f"{region}.{suffix}"
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass

    def record_finder(
        self,
        frame: np.ndarray,
        *,
        finder: LocatedRegion,
        layout: FinderPanelLayout,
        ts_ms: int,
    ) -> None:
        if ts_ms - self._last_finder_ts_ms < self._config.interval_ms:
            return
        self._last_finder_ts_ms = ts_ms

        context = _context_rect(
            finder.rect,
            frame=frame,
            padding=max(self._config.context_padding_px, round(18 * finder.scale)),
        )
        image = _crop_copy(frame, context)
        if image is None:
            return

        _draw_full_rect(image, finder.rect, context=context, label="FINDER", color=(40, 40, 255))
        relative_rects = {
            "RADAR": layout.radar,
            "MODES": layout.modes,
            "DETAILS": layout.details,
            "STATUS": layout.status,
            "UNITS": layout.units,
        }
        colors = {
            "RADAR": (255, 180, 40),
            "MODES": (255, 220, 40),
            "DETAILS": (40, 220, 40),
            "STATUS": (40, 180, 255),
            "UNITS": (220, 80, 220),
        }
        inner_rects: dict[str, list[int]] = {}
        for label, relative in relative_rects.items():
            absolute = _absolute_relative_rect(finder.rect, relative)
            inner_rects[label.lower()] = _rect_values(absolute)
            _draw_full_rect(
                image,
                absolute,
                context=context,
                label=label,
                color=colors[label],
            )

        _draw_header(
            image,
            f"Finder rect={_rect_tuple_text(finder.rect)} conf={finder.confidence:.3f} scale={finder.scale:.3f}",
        )
        self._write(
            "finder",
            image,
            {
                "region": "finder",
                "capturedTsMs": ts_ms,
                "rect": _rect_values(finder.rect),
                "confidence": finder.confidence,
                "scale": finder.scale,
                "innerRects": inner_rects,
            },
        )

    def record_compass(
        self,
        frame: np.ndarray,
        *,
        compass: LocatedCompass,
        rois: CoordinateRois | None,
        ts_ms: int,
    ) -> None:
        if ts_ms - self._last_compass_ts_ms < self._config.interval_ms:
            return
        self._last_compass_ts_ms = ts_ms

        context = _context_rect(
            compass.rect,
            frame=frame,
            padding=max(self._config.context_padding_px, round(18 * compass.scale)),
        )
        image = _crop_copy(frame, context)
        if image is None:
            return

        _draw_full_rect(image, compass.rect, context=context, label="COMPASS", color=(40, 40, 255))
        center = (
            round(compass.center_x - context.x1),
            round(compass.center_y - context.y1),
        )
        cv2.circle(image, center, max(1, round(compass.radius)), (255, 180, 40), 1, cv2.LINE_AA)

        inner_rects: dict[str, list[int]] = {}
        if rois is not None:
            for label, local_rect, color in (
                ("LON", rois.lon, (40, 220, 40)),
                ("LAT", rois.lat, (40, 180, 255)),
            ):
                absolute = _offset_rect(local_rect, dx=compass.rect.x1, dy=compass.rect.y1)
                inner_rects[label.lower()] = _rect_values(absolute)
                _draw_full_rect(
                    image,
                    absolute,
                    context=context,
                    label=label,
                    color=color,
                )

        _draw_header(
            image,
            f"Compass rect={_rect_tuple_text(compass.rect)} conf={compass.confidence:.3f} scale={compass.scale:.3f}",
        )
        self._write(
            "compass",
            image,
            {
                "region": "compass",
                "capturedTsMs": ts_ms,
                "rect": _rect_values(compass.rect),
                "confidence": compass.confidence,
                "scale": compass.scale,
                "center": [compass.center_x, compass.center_y],
                "radius": compass.radius,
                "innerRects": inner_rects,
            },
        )

    def _write(self, region: str, image: np.ndarray, metadata: dict[str, object]) -> None:
        self._config.root_dir.mkdir(parents=True, exist_ok=True)
        png_path = self._config.root_dir / f"{region}.png"
        json_path = self._config.root_dir / f"{region}.json"
        temp_png = self._config.root_dir / f".{region}.png.tmp"
        temp_json = self._config.root_dir / f".{region}.json.tmp"

        ok, encoded = cv2.imencode(".png", image)
        if not ok:
            return
        temp_png.write_bytes(encoded.tobytes())
        temp_json.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
        temp_png.replace(png_path)
        temp_json.replace(json_path)


def _context_rect(rect: RoiRect, *, frame: np.ndarray, padding: int) -> RoiRect:
    height = int(frame.shape[0])
    width = int(frame.shape[1])
    return RoiRect(
        x1=max(0, rect.x1 - padding),
        x2=min(width, rect.x2 + padding),
        y1=max(0, rect.y1 - padding),
        y2=min(height, rect.y2 + padding),
    )


def _crop_copy(frame: np.ndarray, rect: RoiRect) -> np.ndarray | None:
    crop = rect.crop(frame)
    return None if crop is None else crop.copy()


def _absolute_relative_rect(parent: RoiRect, rect: RelativeRect) -> RoiRect:
    width = parent.x2 - parent.x1
    height = parent.y2 - parent.y1
    x1, y1, x2, y2 = rect
    return RoiRect(
        x1=parent.x1 + round(x1 * width),
        x2=parent.x1 + round(x2 * width),
        y1=parent.y1 + round(y1 * height),
        y2=parent.y1 + round(y2 * height),
    )


def _offset_rect(rect: RoiRect, *, dx: int, dy: int) -> RoiRect:
    return RoiRect(
        x1=rect.x1 + dx,
        x2=rect.x2 + dx,
        y1=rect.y1 + dy,
        y2=rect.y2 + dy,
    )


def _draw_full_rect(
    image: np.ndarray,
    rect: RoiRect,
    *,
    context: RoiRect,
    label: str,
    color: tuple[int, int, int],
) -> None:
    x1 = rect.x1 - context.x1
    x2 = rect.x2 - context.x1
    y1 = rect.y1 - context.y1
    y2 = rect.y2 - context.y1
    cv2.rectangle(image, (x1, y1), (x2 - 1, y2 - 1), color, 1, cv2.LINE_AA)
    text_y = max(12, y1 - 3)
    cv2.putText(
        image,
        label,
        (max(1, x1 + 2), text_y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.38,
        color,
        1,
        cv2.LINE_AA,
    )


def _draw_header(image: np.ndarray, text: str) -> None:
    cv2.rectangle(image, (0, 0), (image.shape[1] - 1, 18), (0, 0, 0), -1)
    cv2.putText(
        image,
        text,
        (4, 13),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.34,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )


def _rect_values(rect: RoiRect) -> list[int]:
    return [rect.x1, rect.y1, rect.x2, rect.y2]


def _rect_tuple_text(rect: RoiRect) -> str:
    return f"({rect.x1},{rect.y1},{rect.x2},{rect.y2})"
