from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

CompassRecoveryAction = Literal["keep", "use_layout", "relocate_compass"]


@dataclass(frozen=True, slots=True)
class CompassRecoveryConfig:
    consecutive_failures_before_adjust: int = 3


@dataclass(frozen=True, slots=True)
class CompassRecoveryDecision:
    action: CompassRecoveryAction
    layout_index: int


class CompassRecoveryPolicy:
    """Apply hysteresis before moving coordinate lines or reacquiring the Compass.

    A successful OCR read resets the failure streak and keeps the current layout.
    Repeated failures first advance through nearby line-layout variants. Only after
    all variants have been tried does the policy request a full Compass relocation.
    """

    def __init__(
        self,
        *,
        layout_count: int,
        config: CompassRecoveryConfig | None = None,
    ) -> None:
        if layout_count <= 0:
            raise ValueError("layout_count must be positive")
        self._layout_count = layout_count
        self._config = config or CompassRecoveryConfig()
        if self._config.consecutive_failures_before_adjust <= 0:
            raise ValueError("consecutive_failures_before_adjust must be positive")
        self._layout_index = 0
        self._consecutive_failures = 0

    @property
    def layout_index(self) -> int:
        return self._layout_index

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    def observe(self, *, read_healthy: bool) -> CompassRecoveryDecision:
        if read_healthy:
            self._consecutive_failures = 0
            return CompassRecoveryDecision(action="keep", layout_index=self._layout_index)

        self._consecutive_failures += 1
        if self._consecutive_failures < self._config.consecutive_failures_before_adjust:
            return CompassRecoveryDecision(action="keep", layout_index=self._layout_index)

        self._consecutive_failures = 0
        next_index = self._layout_index + 1
        if next_index < self._layout_count:
            self._layout_index = next_index
            return CompassRecoveryDecision(action="use_layout", layout_index=self._layout_index)

        self._layout_index = 0
        return CompassRecoveryDecision(action="relocate_compass", layout_index=0)

    def reset_after_relocation(self) -> None:
        self._layout_index = 0
        self._consecutive_failures = 0
