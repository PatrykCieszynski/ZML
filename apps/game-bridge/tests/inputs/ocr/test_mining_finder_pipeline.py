from __future__ import annotations

import numpy as np

from zml_game_bridge.domain.mining import MiningMode
from zml_game_bridge.inputs.ocr.pipelines.mining_finder.model import FinderFeatures
from zml_game_bridge.inputs.ocr.pipelines.mining_finder.parsing import (
    classify_status,
    parse_units_text,
)
from zml_game_bridge.inputs.ocr.pipelines.mining_finder.pipeline import (
    MiningFinderPipeline,
    MiningFinderPipelineConfig,
)


class FakeFeatureDetector:
    def __init__(self, *features: FinderFeatures) -> None:
        self._features = list(features)
        self.closed = False

    def detect(self, _finder_roi: np.ndarray) -> FinderFeatures:
        if not self._features:
            return FinderFeatures()
        return self._features.pop(0)

    def close(self) -> None:
        self.closed = True


def test_mining_finder_pipeline_emits_probe_fired_on_sending_probe_status() -> None:
    pipeline = MiningFinderPipeline(
        detector=FakeFeatureDetector(
            FinderFeatures(modes_mask=int(MiningMode.ORE), status_kind="idle"),
            FinderFeatures(modes_mask=int(MiningMode.ORE), status_kind="idle"),
            FinderFeatures(
                modes_mask=int(MiningMode.ORE),
                status_kind="sending_probe",
                raw_status_text="Sending probe...",
            ),
            FinderFeatures(modes_mask=int(MiningMode.ORE), status_kind="sending_probe"),
        )
    )

    assert [signal.kind for signal in pipeline.step(_roi(), 1_000)] == []
    assert [signal.kind for signal in pipeline.step(_roi(), 1_100)] == ["finder_modes_changed"]

    signals = pipeline.step(_roi(), 1_200)
    assert [signal.kind for signal in signals] == ["probe_fired"]
    assert signals[0].modes_mask == int(MiningMode.ORE)
    assert signals[0].raw_text == "Sending probe..."

    assert pipeline.step(_roi(), 1_300) == []


def test_mining_finder_pipeline_applies_probe_cooldown() -> None:
    pipeline = MiningFinderPipeline(
        detector=FakeFeatureDetector(
            FinderFeatures(status_kind="sending_probe"),
            FinderFeatures(status_kind="idle"),
            FinderFeatures(status_kind="sending_probe"),
        ),
        cfg=MiningFinderPipelineConfig(probe_cooldown_ms=900),
    )

    assert [signal.kind for signal in pipeline.step(_roi(), 1_000)] == ["probe_fired"]
    assert pipeline.step(_roi(), 1_100) == []
    assert pipeline.step(_roi(), 1_500) == []


def test_mining_finder_pipeline_emits_mode_invalidated_when_icons_drop_to_none() -> None:
    pipeline = MiningFinderPipeline(
        detector=FakeFeatureDetector(
            FinderFeatures(modes_mask=int(MiningMode.ORE | MiningMode.ENMATTER)),
            FinderFeatures(modes_mask=int(MiningMode.ORE | MiningMode.ENMATTER)),
            FinderFeatures(modes_mask=int(MiningMode.NONE)),
            FinderFeatures(modes_mask=int(MiningMode.NONE)),
        )
    )

    assert pipeline.step(_roi(), 1_000) == []
    changed = pipeline.step(_roi(), 1_100)
    assert pipeline.step(_roi(), 1_200) == []
    invalidated = pipeline.step(_roi(), 1_300)

    assert [signal.kind for signal in changed] == ["finder_modes_changed"]
    assert changed[0].modes_mask == int(MiningMode.ORE | MiningMode.ENMATTER)
    assert [signal.kind for signal in invalidated] == ["finder_mode_invalidated"]
    assert invalidated[0].previous_modes_mask == int(MiningMode.ORE | MiningMode.ENMATTER)


def test_mining_finder_pipeline_uses_recent_valid_modes_when_current_mode_is_none() -> None:
    pipeline = MiningFinderPipeline(
        detector=FakeFeatureDetector(
            FinderFeatures(modes_mask=int(MiningMode.ORE)),
            FinderFeatures(modes_mask=int(MiningMode.ORE)),
            FinderFeatures(modes_mask=int(MiningMode.NONE)),
            FinderFeatures(modes_mask=int(MiningMode.NONE)),
            FinderFeatures(modes_mask=int(MiningMode.NONE), status_kind="sending_probe"),
        ),
        cfg=MiningFinderPipelineConfig(invalid_mode_grace_ms=2_000),
    )

    pipeline.step(_roi(), 1_000)
    pipeline.step(_roi(), 1_100)
    pipeline.step(_roi(), 1_200)
    pipeline.step(_roi(), 1_300)
    signals = pipeline.step(_roi(), 1_400)

    assert [signal.kind for signal in signals] == ["probe_fired"]
    assert signals[0].modes_mask == int(MiningMode.ORE)


def test_mining_finder_pipeline_emits_units_after_stable_read() -> None:
    pipeline = MiningFinderPipeline(
        detector=FakeFeatureDetector(
            FinderFeatures(probes_per_drop=0, ammo_per_drop=13_000, raw_units_text="13000"),
            FinderFeatures(probes_per_drop=0, ammo_per_drop=13_000, raw_units_text="13000"),
        )
    )

    assert pipeline.step(_roi(), 1_000) == []
    signals = pipeline.step(_roi(), 1_100)

    assert [signal.kind for signal in signals] == ["finder_units_changed"]
    assert signals[0].ammo_per_drop == 13_000


def test_parse_units_text_distinguishes_probes_from_ammo() -> None:
    assert parse_units_text("PROBES\n2") == (2, None)
    assert parse_units_text("UNIVERSAL AMMO\n1000") == (None, 1000)


def test_classify_status_distinguishes_no_resources_from_preclaim_found() -> None:
    assert classify_status("No resources found. Try again\nsomewhere else-") == "no_resources"
    assert (
        classify_status(
            "You have found a resource. Follow\n"
            "the arrows to its location.\n"
            "Estimated size: Minimal (1)"
        )
        == "found"
    )


def test_mining_finder_pipeline_emits_hit_hint_for_found_status() -> None:
    pipeline = MiningFinderPipeline(
        detector=FakeFeatureDetector(
            FinderFeatures(
                status_kind="found",
                hit_size_label="Minimal",
                hit_size_index=1,
                resource_name="Lysterium Stone",
                range_m=8.8,
                depth_m=125.0,
                raw_status_text=(
                    "You have found a resource. Follow the arrows to its location.\n"
                    "Estimated size: Minimal (1)"
                ),
                raw_details_text="RANGE 8.8m\nDEPTH 125m\nTYPE Lysterium Stone",
            ),
            FinderFeatures(
                status_kind="found",
                hit_size_label="Minimal",
                hit_size_index=1,
                resource_name="Lysterium Stone",
                range_m=8.8,
                depth_m=125.0,
            ),
        )
    )

    signals = pipeline.step(_roi(), 1_000)
    assert [signal.kind for signal in signals] == ["finder_hit_hint"]
    assert signals[0].resource_name == "Lysterium Stone"
    assert signals[0].hit_size_label == "Minimal"
    assert signals[0].hit_size_index == 1
    assert signals[0].range_m == 8.8
    assert signals[0].depth_m == 125.0

    assert pipeline.step(_roi(), 1_100) == []


def test_mining_finder_pipeline_does_not_reemit_hit_hint_when_found_range_changes() -> None:
    pipeline = MiningFinderPipeline(
        detector=FakeFeatureDetector(
            FinderFeatures(
                status_kind="found",
                hit_size_label="Minimal",
                hit_size_index=1,
                resource_name="Lysterium Stone",
                range_m=8.8,
                depth_m=125.0,
            ),
            FinderFeatures(
                status_kind="found",
                hit_size_label="Minimal",
                hit_size_index=1,
                resource_name="Lysterium Stone",
                range_m=5.2,
                depth_m=125.0,
            ),
            FinderFeatures(status_kind="searching"),
            FinderFeatures(
                status_kind="found",
                hit_size_label="Small",
                hit_size_index=2,
                resource_name="Belkar Stone",
                range_m=12.0,
                depth_m=110.0,
            ),
        )
    )

    assert [signal.kind for signal in pipeline.step(_roi(), 1_000)] == ["finder_hit_hint"]
    assert pipeline.step(_roi(), 1_100) == []
    assert pipeline.step(_roi(), 1_200) == []
    assert [signal.kind for signal in pipeline.step(_roi(), 1_300)] == ["finder_hit_hint"]


def test_mining_finder_pipeline_ignores_mode_reads_during_found_overlay() -> None:
    pipeline = MiningFinderPipeline(
        detector=FakeFeatureDetector(
            FinderFeatures(modes_mask=int(MiningMode.ORE), status_kind="idle"),
            FinderFeatures(modes_mask=int(MiningMode.ORE), status_kind="idle"),
            FinderFeatures(
                modes_mask=int(MiningMode.ORE),
                status_kind="found",
                hit_size_label="Minimal",
                hit_size_index=1,
                resource_name="Lysterium Stone",
            ),
            FinderFeatures(modes_mask=int(MiningMode.ORE | MiningMode.ENMATTER | MiningMode.TREASURE)),
            FinderFeatures(modes_mask=int(MiningMode.NONE), status_kind="sending_probe"),
        )
    )

    pipeline.step(_roi(), 1_000)
    pipeline.step(_roi(), 1_100)
    pipeline.step(_roi(), 1_200)
    pipeline.step(_roi(), 1_300)
    signals = pipeline.step(_roi(), 1_400)

    assert [signal.kind for signal in signals] == ["probe_fired"]
    assert signals[0].modes_mask == int(MiningMode.ORE)


def test_mining_finder_pipeline_closes_detector() -> None:
    detector = FakeFeatureDetector()
    pipeline = MiningFinderPipeline(detector=detector)

    pipeline.close()

    assert detector.closed is True


def _roi() -> np.ndarray:
    return np.zeros((64, 128, 3), dtype=np.uint8)
