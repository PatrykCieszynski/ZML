from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass(frozen=True, slots=True)
class RoiRect:
    x1: int
    x2: int
    y1: int
    y2: int

    def crop(self, frame: np.ndarray) -> Optional[np.ndarray]:
        h: int = int(frame.shape[0])
        w: int = int(frame.shape[1])

        x1 = max(0, min(self.x1, w))
        x2 = max(0, min(self.x2, w))
        y1 = max(0, min(self.y1, h))
        y2 = max(0, min(self.y2, h))
        if x2 <= x1 or y2 <= y1:
            return None

        roi = frame[y1:y2, x1:x2]
        roi = np.ascontiguousarray(roi)

        if roi.dtype != np.uint8:
            raise ValueError(f"Unsupported ROI dtype: {roi.dtype}")

        return roi
