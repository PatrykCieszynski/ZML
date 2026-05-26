from __future__ import annotations

import argparse
from pathlib import Path

import cv2

from zml_game_bridge.inputs.ocr.pipelines.mining_finder.pipeline import (
    MiningFinderPipeline,
)
from zml_game_bridge.inputs.ocr.pipelines.mining_finder.recording import (
    default_finder_recording_dir,
)
from zml_game_bridge.inputs.ocr.pipelines.mining_finder.vision import (
    VisionFinderFeatureDetector,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=default_finder_recording_dir(),
        help="Folder with finder crop PNG/JPG files.",
    )
    args = parser.parse_args()

    paths = sorted(
        path
        for path in args.root.iterdir()
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
    )
    if not paths:
        raise FileNotFoundError(f"No finder crop images found in {args.root}")

    feature_detector = VisionFinderFeatureDetector()
    pipeline = MiningFinderPipeline(detector=VisionFinderFeatureDetector())

    print(
        "file,shape,status_kind,modes_mask,radar_signal_active,radar_blue_score,"
        "radar_change_score,radar_center_blue_score,mode_ore_score,mode_enmatter_score,"
        "mode_treasure_score,units_text,details_text,resource,size,range_m,depth_m,signals"
    )

    try:
        for index, path in enumerate(paths):
            img = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
            if img is None:
                print(f"{path.name},READ_FAILED,,,,,,,,,")
                continue

            ts_ms = 1_000 + index * 100
            features = feature_detector.detect(img)
            signals = pipeline.step(img, ts_ms)
            debug = features.debug
            signal_names = "|".join(signal.kind for signal in signals)
            size = ""
            if features.hit_size_label is not None and features.hit_size_index is not None:
                size = f"{features.hit_size_label} ({features.hit_size_index})"
            print(
                f"{path.name},{tuple(img.shape)},{features.status_kind},{features.modes_mask},"
                f"{features.radar_signal_active},"
                f"{debug.get('radar_blue_score', 0.0):.4f},"
                f"{debug.get('radar_change_score', 0.0):.4f},"
                f"{debug.get('radar_center_blue_score', 0.0):.4f},"
                f"{debug.get('mode_ore_score', 0.0):.4f},"
                f"{debug.get('mode_enmatter_score', 0.0):.4f},"
                f"{debug.get('mode_treasure_score', 0.0):.4f},"
                f"{_csv_cell(features.raw_units_text)},"
                f"{_csv_cell(features.raw_details_text)},"
                f"{_csv_cell(features.resource_name)},"
                f"{_csv_cell(size)},"
                f"{features.range_m if features.range_m is not None else ''},"
                f"{features.depth_m if features.depth_m is not None else ''},"
                f"{signal_names}"
            )
    finally:
        pipeline.close()

    return 0


def _csv_cell(value: str | None) -> str:
    if value is None:
        return ""
    return '"' + value.replace('"', '""').replace("\n", "\\n") + '"'


if __name__ == "__main__":
    raise SystemExit(main())
