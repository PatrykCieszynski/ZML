from __future__ import annotations

import sys

import pytest
from zml_ocr_protocol import ShutdownCommand, ShutdownPayload, decode_bridge_message

from zml_game_bridge.runtime.ocr_agent.process_transport import (
    OcrAgentProcessConfig,
    StdioOcrProcessTransport,
    normalize_command,
)


@pytest.mark.timeout(2)
def test_stdio_transport_writes_and_reads_protocol_lines() -> None:
    transport = StdioOcrProcessTransport(
        OcrAgentProcessConfig(
            command=(
                sys.executable,
                "-c",
                "import sys; line=sys.stdin.buffer.readline(); "
                "sys.stdout.buffer.write(line); sys.stdout.buffer.flush()",
            ),
            environment={"ZML_TRANSPORT_TEST": "1"},
        )
    )
    command = ShutdownCommand(
        protocol_version=1,
        type="shutdown",
        command_id="a" * 32,
        sent_ts_ms=1,
        payload=ShutdownPayload(reason="backend_shutdown"),
    )

    transport.start()
    transport.send(command)
    echoed = decode_bridge_message(transport.read_stdout_line())

    assert echoed == command
    assert transport.wait(timeout_s=1.0) == 0


def test_normalize_command_rejects_an_empty_command() -> None:
    assert normalize_command(["python", "", "  ", "-m", "zml_ocr_agent"]) == (
        "python",
        "-m",
        "zml_ocr_agent",
    )
    with pytest.raises(ValueError, match="cannot be empty"):
        normalize_command(["", "  "])
