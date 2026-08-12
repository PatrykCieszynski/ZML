from __future__ import annotations

from collections import deque

import numpy as np

from zml_ocr_worker.calibration.model import LocatedCompass
from zml_ocr_worker.calibration.multiframe_compass import (
    MultiFrameCompassLocator,
    MultiFrameCompassLocatorConfig,
)
from zml_ocr_worker.capture.model import RoiRect


class _StubMultiFrameLocator(MultiFrameCompassLocator):
    def __init__(self, *samples: LocatedCompass | None) -> None:
        super().__init__(
            config=MultiFrameCompassLocatorConfig(
                sample_count=7,
                min_inliers=5,
            )
        )
        self._stub_samples = deque(samples)

    def _locate_single(self, frame: np.ndarray) -> LocatedCompass | None:
        if not self._stub_samples:
            return None
        return self._stub_samples.popleft()

    def locked_is_valid(self, frame: np.ndarray, compass: LocatedCompass) -> bool:
        return True


def _compass(*, dx: int = 0, dy: int = 0, dr: int = 0) -> LocatedCompass:
    return LocatedCompass(
        rect=RoiRect(
            x1=100 + dx,
            x2=360 + dx,
            y1=80 + dy,
            y2=400 + dy,
        ),
        confidence=0.95,
        scale=1.0 + dr / 100.0,
        center_x=230.0 + dx,
        center_y=230.0 + dy,
        radius=100.0 + dr,
    )


def test_multiframe_locator_uses_consensus_and_rejects_single_outlier() -> None:
    locator = _StubMultiFrameLocator(
        _compass(dx=-1),
        _compass(dy=1),
        _compass(dx=1),
        _compass(dr=1),
        _compass(dx=-1, dy=-1),
        _compass(),
        _compass(dx=80, dy=-60, dr=35),
    )
    frame = np.zeros((500, 500, 3), dtype=np.uint8)

    for _ in range(6):
        assert locator.locate(frame) is None
        assert locator.acquiring

    result = locator.locate(frame)

    assert result is not None
    assert not locator.acquiring
    assert abs(result.center_x - 230.0) <= 1.0
    assert abs(result.center_y - 230.0) <= 1.0
    assert abs(result.radius - 100.0) <= 1.0
    assert result.rect.x1 == 100
    assert result.rect.x2 == 360


def test_multiframe_locator_requires_consecutive_successful_frames() -> None:
    locator = _StubMultiFrameLocator(
        _compass(),
        _compass(),
        None,
        _compass(),
        _compass(),
        _compass(),
        _compass(),
        _compass(),
        _compass(),
        _compass(),
    )
    frame = np.zeros((500, 500, 3), dtype=np.uint8)

    assert locator.locate(frame) is None
    assert locator.locate(frame) is None
    assert locator.acquiring
    assert locator.locate(frame) is None
    assert not locator.acquiring

    result = None
    for _ in range(7):
        result = locator.locate(frame)

    assert result is not None
