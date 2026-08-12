from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from zml_ocr_worker.pipelines.mining_finder.model import FinderFeatures, MiningFinderSignal
from zml_ocr_worker.pipelines.mining_finder.recording import (
    FinderCropRecorder,
    FinderRecordingConfig,
)


def test_accepted_recording_writes_annotated_hit_with_resource_and_size(tmp_path: Path) -> None:
    recorder = FinderCropRecorder(
        config=FinderRecordingConfig(
            modes=frozenset({"accepted"}),
            root_dir=tmp_path,
            max_samples=10,
        ),
        roi_name="finder_auto",
    )
    crop = np.zeros((239, 347, 4), dtype=np.uint8)
    features = FinderFeatures(
        status_kind="found",
        hit_size_label="Considerable",
        hit_size_index=5,
        resource_name="Garcen Grease",
        raw_status_text="Estimated size: Considerable (5)",
        raw_details_text="RANGE 8.8m\nDEPTH 125m\nTYPE Garcen Grease",
    )
    signal = MiningFinderSignal(
        ts_ms=1_000,
        kind="finder_hit_hint",
        hit_size_label="Considerable",
        hit_size_index=5,
        resource_name="Garcen Grease",
    )

    recorder.record_accepted_frame(crop, ts_ms=1_000)
    recorder.record_frame(
        crop,
        ts_ms=1_000,
        features=features,
        signals=[signal],
    )

    annotated_files = list(tmp_path.glob("*_hit_*_annotated.png"))
    assert len(annotated_files) == 1
    annotated = cv2.imread(str(annotated_files[0]), cv2.IMREAD_COLOR)
    assert annotated is not None
    assert annotated.shape[0] > crop.shape[0]
    assert annotated.shape[1] == crop.shape[1]
    assert np.count_nonzero(annotated) > 0

    metadata_path = annotated_files[0].with_suffix(".json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["phase"] == "hit_annotated"
    assert metadata["features"]["resource_name"] == "Garcen Grease"
    assert metadata["features"]["hit_size_label"] == "Considerable"
    assert metadata["features"]["hit_size_index"] == 5
    assert metadata["signals"][0]["kind"] == "finder_hit_hint"


def test_accepted_recording_does_not_annotate_non_hit_frames(tmp_path: Path) -> None:
    recorder = FinderCropRecorder(
        config=FinderRecordingConfig(
            modes=frozenset({"accepted"}),
            root_dir=tmp_path,
            max_samples=10,
        ),
        roi_name="finder_auto",
    )
    crop = np.zeros((239, 347, 4), dtype=np.uint8)

    recorder.record_accepted_frame(crop, ts_ms=1_000)
    recorder.record_frame(
        crop,
        ts_ms=1_000,
        features=FinderFeatures(status_kind="no_resources"),
        signals=[MiningFinderSignal(ts_ms=1_000, kind="finder_no_resources")],
    )

    assert list(tmp_path.glob("*_hit_*_annotated.png")) == []
