from __future__ import annotations

from zml_game_bridge.events.base import SignalBase, should_persist_event
from zml_game_bridge.inputs.ocr.signals import (
    FinderHitHint,
    FinderModeInvalidated,
    FinderModesChanged,
    FinderUnitsChanged,
    ProbeFired,
)


def test_finder_ocr_signals_are_transient() -> None:
    signals = [
        ProbeFired(ts_ms=1, position=None, modes_mask=1, ammo_per_drop=1_000),
        FinderModesChanged(ts_ms=1, modes_mask=1, previous_modes_mask=None),
        FinderModeInvalidated(ts_ms=1, previous_modes_mask=1),
        FinderUnitsChanged(ts_ms=1, probes_per_drop=None, ammo_per_drop=1_000),
        FinderHitHint(
            ts_ms=1,
            size_label="Minimal",
            size_index=1,
            resource_name="Lysterium Stone",
        ),
    ]

    assert all(isinstance(signal, SignalBase) for signal in signals)
    assert all(not should_persist_event(signal) for signal in signals)
