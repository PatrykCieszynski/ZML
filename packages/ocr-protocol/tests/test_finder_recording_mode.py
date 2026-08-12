from __future__ import annotations

from zml_ocr_protocol.messages import FinderRecordingConfigPayload


def test_finder_recording_config_accepts_accepted_mode() -> None:
    payload = FinderRecordingConfigPayload(
        modes=["accepted"],
        directory="C:/zml/ocr/finder-crops",
        interval_ms=60_000,
        max_samples=1000,
    )

    assert payload.modes == ["accepted"]
