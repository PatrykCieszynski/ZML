from __future__ import annotations

from zml_backend.application.mining.signals.finder import (
    FinderHitHintSignal,
    FinderModeInvalidatedSignal,
    FinderModesChangedSignal,
    FinderNoResourcesSignal,
    FinderUnitsChangedSignal,
    ProbeFiredSignal,
)
from zml_backend.events.base import SignalBase, should_persist_event


def test_finder_signals_are_transient() -> None:
    signals = [
        ProbeFiredSignal(ts_ms=1, position=None, modes_mask=1, ammo_per_drop=1_000),
        FinderModesChangedSignal(ts_ms=1, modes_mask=1, previous_modes_mask=None),
        FinderModeInvalidatedSignal(ts_ms=1, previous_modes_mask=1),
        FinderUnitsChangedSignal(ts_ms=1, probes_per_drop=None, ammo_per_drop=1_000),
        FinderHitHintSignal(
            ts_ms=1,
            size_label="Minimal",
            size_index=1,
            resource_name="Lysterium Stone",
        ),
        FinderNoResourcesSignal(ts_ms=1),
    ]

    assert all(isinstance(signal, SignalBase) for signal in signals)
    assert all(not should_persist_event(signal) for signal in signals)
