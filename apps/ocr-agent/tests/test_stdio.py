from __future__ import annotations

from io import BytesIO

from zml_ocr_protocol import HeartbeatMessage, HelloMessage, decode_agent_message

from zml_ocr_agent.message_factory import AgentMessageFactory
from zml_ocr_agent.stdio import AgentRuntimeState, ProtocolWriter


def test_protocol_writer_assigns_wire_sequence_in_emission_order() -> None:
    output = BytesIO()
    runtime_state = AgentRuntimeState()
    writer = ProtocolWriter(output, runtime_state=runtime_state)
    factory = AgentMessageFactory(
        clock_ms=lambda: 100,
        message_id_factory=lambda: "a" * 32,
    )
    hello = factory.hello()
    status = factory.status(
        state="waiting_for_window",
        capture_available=False,
        code="window_unavailable",
        detail="window missing",
    )
    heartbeat = factory.heartbeat(state="degraded", capture_available=False)

    writer.write(hello)
    writer.write(heartbeat)
    writer.write(status)

    messages = [decode_agent_message(line) for line in output.getvalue().splitlines()]
    assert len(messages) == 3
    assert isinstance(messages[0], HelloMessage)
    assert isinstance(messages[1], HeartbeatMessage)
    assert [message.sequence_id for message in messages] == [0, 1, 2]


def test_runtime_state_tracks_latest_status_for_heartbeat() -> None:
    runtime_state = AgentRuntimeState()
    factory = AgentMessageFactory(
        clock_ms=lambda: 100,
        message_id_factory=lambda: "a" * 32,
    )

    runtime_state.observe(
        factory.status(
            state="waiting_for_window",
            capture_available=False,
            code="window_unavailable",
            detail="window missing",
        )
    )

    assert runtime_state.snapshot() == ("waiting_for_window", False)
