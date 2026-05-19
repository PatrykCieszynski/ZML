from __future__ import annotations

# Backward-compatible import path. OCR finder outputs are operational signals,
# not durable domain events; new code should import from inputs.ocr.signals.
from zml_game_bridge.inputs.ocr.signals import (
    FinderHitHint,
    FinderModeInvalidated,
    FinderModesChanged,
    FinderUnitsChanged,
    ProbeFired,
)

__all__ = [
    "FinderHitHint",
    "FinderModeInvalidated",
    "FinderModesChanged",
    "FinderUnitsChanged",
    "ProbeFired",
]
