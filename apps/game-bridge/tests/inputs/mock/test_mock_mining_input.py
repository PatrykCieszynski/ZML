from __future__ import annotations

from zml_game_bridge.inputs.mock.mining import iter_mock_mining_signals
from zml_game_bridge.inputs.ocr.pipelines.mining_finder.signals import (
    FinderHitHintSignal,
    FinderModesChangedSignal,
    FinderNoResourcesSignal,
    FinderUnitsChangedSignal,
    ProbeFiredSignal,
)


def test_iter_mock_mining_signals_emits_setup_and_predictable_drop_results() -> None:
    signals = list(iter_mock_mining_signals(start_ts_ms=1_000, drop_count=3))

    assert isinstance(signals[0], FinderModesChangedSignal)
    assert isinstance(signals[1], FinderUnitsChangedSignal)
    assert [type(signal) for signal in signals[2:]] == [
        ProbeFiredSignal,
        FinderNoResourcesSignal,
        ProbeFiredSignal,
        FinderNoResourcesSignal,
        ProbeFiredSignal,
        FinderHitHintSignal,
    ]

    first_drop = signals[2]
    second_drop = signals[4]
    assert isinstance(first_drop, ProbeFiredSignal)
    assert isinstance(second_drop, ProbeFiredSignal)
    assert first_drop.position is not None
    assert second_drop.position is not None
    assert abs(second_drop.position.x - first_drop.position.x) <= 20
    assert abs(second_drop.position.y - first_drop.position.y) <= 20

    hit = signals[-1]
    assert isinstance(hit, FinderHitHintSignal)
    assert hit.resource_name == "Lysterium Stone"
    assert hit.range_m == 51.14
