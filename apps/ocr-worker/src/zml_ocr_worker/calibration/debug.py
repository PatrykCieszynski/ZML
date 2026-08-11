from __future__ import annotations

import json
from pathlib import Path

import cv2

from zml_ocr_worker.calibration.compass import CompassLocator
from zml_ocr_worker.calibration.coordinates import CompassCoordinateLayout
from zml_ocr_worker.calibration.finder import FinderLocator
from zml_ocr_worker.calibration.model import LocatedCompass, LocatedRegion
from zml_ocr_worker.pipelines.position.pipeline import PositionPipeline, PositionReadResult


def run_calibration_debug(image_path: Path, *, annotated_path: Path | None = None) -> int:
    frame = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError(f"Could not read image: {image_path}")

    finder = FinderLocator().locate(frame)
    compass = CompassLocator().locate(frame)
    coordinate_payload: dict[str, object] | None = None
    if compass is not None:
        coordinate_payload = _read_coordinates(frame, compass)

    payload = {
        "image": {
            "width": int(frame.shape[1]),
            "height": int(frame.shape[0]),
        },
        "finder": _region_payload(finder),
        "compass": _compass_payload(compass, coordinates=coordinate_payload),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))

    if annotated_path is not None:
        annotated = frame.copy()
        if finder is not None:
            _draw_region(annotated, finder, label="Finder")
        if compass is not None:
            _draw_region(annotated, compass, label="Compass")
            cv2.circle(
                annotated,
                (round(compass.center_x), round(compass.center_y)),
                round(compass.radius),
                (255, 255, 255),
                1,
            )
        annotated_path.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(annotated_path), annotated):
            raise OSError(f"Could not write annotated image: {annotated_path}")

    return 0 if finder is not None or compass is not None else 2


def _read_coordinates(frame, compass: LocatedCompass) -> dict[str, object]:
    compass_roi = compass.rect.crop(frame)
    if compass_roi is None:
        return {"longitude": None, "latitude": None, "hasPosition": False}

    variants = CompassCoordinateLayout().variants(compass)
    pipeline = PositionPipeline(variants[0].roi_candidates[0])
    try:
        last = PositionReadResult(longitude=None, latitude=None, position=None)
        for index, variant in enumerate(variants):
            last = pipeline.read_candidates(compass_roi, 0, variant.roi_candidates)
            if last.valid:
                return {
                    "longitude": last.longitude,
                    "latitude": last.latitude,
                    "hasPosition": True,
                    "layoutIndex": index,
                    "verticalOffsetRadius": variant.vertical_offset_radius,
                }
        return {
            "longitude": last.longitude,
            "latitude": last.latitude,
            "hasPosition": False,
        }
    finally:
        pipeline.close()


def _region_payload(region: LocatedRegion | None) -> dict[str, object] | None:
    if region is None:
        return None
    return {
        "rect": {
            "x": region.rect.x1,
            "y": region.rect.y1,
            "width": region.rect.x2 - region.rect.x1,
            "height": region.rect.y2 - region.rect.y1,
        },
        "confidence": round(region.confidence, 4),
        "scale": round(region.scale, 4),
    }


def _compass_payload(
    compass: LocatedCompass | None,
    *,
    coordinates: dict[str, object] | None,
) -> dict[str, object] | None:
    payload = _region_payload(compass)
    if payload is None or compass is None:
        return None
    payload["radar"] = {
        "centerX": round(compass.center_x, 2),
        "centerY": round(compass.center_y, 2),
        "radius": round(compass.radius, 2),
    }
    payload["coordinates"] = coordinates
    return payload


def _draw_region(frame, region: LocatedRegion, *, label: str) -> None:
    rect = region.rect
    cv2.rectangle(frame, (rect.x1, rect.y1), (rect.x2, rect.y2), (255, 255, 255), 2)
    cv2.putText(
        frame,
        f"{label} {region.confidence:.2f}",
        (rect.x1, max(20, rect.y1 - 8)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
