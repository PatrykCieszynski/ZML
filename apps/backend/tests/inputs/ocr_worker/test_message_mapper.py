from __future__ import annotations

from zml_ocr_protocol.messages import (
    PositionMessage,
    PositionObservationPayload,
    WorldPositionPayload,
)

from zml_backend.application.position.model import PositionSnapshot
from zml_backend.inputs.ocr_worker.message_mapper import OcrWorkerMessageMapper


def test_position_mapper_preserves_confidence() -> None:
    positions: list[PositionSnapshot] = []
    mapper = OcrWorkerMessageMapper(
        position_sink=positions.append,
        signal_sink=lambda _signal: None,
        clock_ms=lambda: 2_000,
    )
    message = PositionMessage(
        protocol_version=1,
        type="position",
        message_id="a" * 32,
        sequence_id=1,
        emitted_ts_ms=1_100,
        observed_ts_ms=1_000,
        payload=PositionObservationPayload(
            position=WorldPositionPayload(
                planet_name="Calypso",
                x=30_683,
                y=9_621,
                z=None,
            ),
            confidence=0.2,
            roi_name="compass_auto",
        ),
    )

    mapper.map_position(message)

    assert len(positions) == 1
    assert positions[0].confidence == 0.2
    assert positions[0].received_ts_ms == 2_000
