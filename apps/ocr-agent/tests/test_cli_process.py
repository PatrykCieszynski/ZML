from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from zml_ocr_protocol import (
    CommandResultMessage,
    HelloMessage,
    decode_agent_message,
    encode_message,
)
from zml_ocr_protocol.messages import ShutdownCommand, ShutdownPayload


def test_version_command() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "zml_ocr_agent", "--version"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "zml-ocr-agent 0.1.0"
    assert result.stderr == ""


@pytest.mark.timeout(15)
def test_stdio_process_emits_hello_accepts_shutdown_and_exits() -> None:
    shutdown = ShutdownCommand(
        protocol_version=1,
        type="shutdown",
        command_id="f" * 32,
        sent_ts_ms=1,
        payload=ShutdownPayload(reason="backend_shutdown"),
    )
    process = subprocess.Popen(
        [sys.executable, "-m", "zml_ocr_agent", "stdio"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    stdout, stderr = process.communicate(input=encode_message(shutdown), timeout=12)

    assert process.returncode == 0, stderr.decode("utf-8", errors="replace")
    messages = [decode_agent_message(line) for line in stdout.splitlines()]
    assert isinstance(messages[0], HelloMessage)
    results = [message for message in messages if isinstance(message, CommandResultMessage)]
    assert len(results) == 1
    assert results[0].payload.command_id == shutdown.command_id
    assert results[0].payload.command_type == "shutdown"
    assert results[0].payload.status == "ok"


def test_agent_source_does_not_import_game_bridge() -> None:
    source_root = Path(__file__).parents[1] / "src" / "zml_ocr_agent"
    offenders = [
        path
        for path in source_root.rglob("*.py")
        if "zml_game_bridge" in path.read_text(encoding="utf-8")
    ]

    assert offenders == []
