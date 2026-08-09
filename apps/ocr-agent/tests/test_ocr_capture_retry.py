from __future__ import annotations

from typing import cast

import numpy as np

from zml_ocr_agent.capture.window_capturer import (
    WindowCapturer,
    WindowCaptureUnavailableError,
)
from zml_ocr_agent.runner import _try_grab_frame


class _RecoveringCapturer:
    def __init__(self) -> None:
        self.attempts = 0
        self.close_calls = 0

    def grab(self) -> np.ndarray:
        self.attempts += 1
        if self.attempts == 1:
            raise WindowCaptureUnavailableError("Entropia window is missing")
        return np.zeros((2, 3, 3), dtype=np.uint8)

    def close(self) -> None:
        self.close_calls += 1


def test_capture_retry_recovers_after_target_window_appears() -> None:
    fake_capturer = _RecoveringCapturer()
    capturer = cast(WindowCapturer, fake_capturer)

    missing_frame, error = _try_grab_frame(capturer)
    recovered_frame, recovered_error = _try_grab_frame(capturer)

    assert missing_frame is None
    assert error == "Entropia window is missing"
    assert fake_capturer.close_calls == 1
    assert recovered_frame is not None
    assert recovered_frame.shape == (2, 3, 3)
    assert recovered_error is None
