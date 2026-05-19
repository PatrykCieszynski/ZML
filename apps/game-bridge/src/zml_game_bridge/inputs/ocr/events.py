from __future__ import annotations

# Backward-compatible import path. OCR finder outputs are operational signals,
# not durable domain events; new code should import from inputs.ocr.signals.
from zml_game_bridge.inputs.ocr.signals import (
    FinderHitHintSignal,
    FinderModeInvalidatedSignal,
    FinderModesChangedSignal,
    FinderNoResourcesSignal,
    FinderUnitsChangedSignal,
    ProbeFiredSignal,
)

__all__ = [
    "FinderHitHintSignal",
    "FinderModeInvalidatedSignal",
    "FinderModesChangedSignal",
    "FinderNoResourcesSignal",
    "FinderUnitsChangedSignal",
    "ProbeFiredSignal",
]
