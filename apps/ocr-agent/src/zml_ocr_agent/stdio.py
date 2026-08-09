from __future__ import annotations

import logging
import sys
import threading
from io import BufferedReader, BufferedWriter
from typing import BinaryIO, cast

from zml_ocr_protocol import (
    OcrProtocolError,
    decode_bridge_message,
    encode_message,
)
from zml_ocr_protocol.messages import AgentToBridgeMessage, BridgeToAgentMessage

from zml_ocr_agent.message_factory import AgentMessageFactory
from zml_ocr_agent.runner import start_ocr_input
from zml_ocr_agent.tesserocr_runtime import preload_tesserocr_preserving_sigint_handler

logger = logging.getLogger(__name__)


class ProtocolWriter:
    def __init__(self, output: BinaryIO) -> None:
        self._output = output
        self._lock = threading.Lock()

    def write(self, message: AgentToBridgeMessage) -> None:
        encoded = encode_message(message)
        with self._lock:
            self._output.write(encoded)
            self._output.flush()


def run_stdio(*, stdin: BinaryIO | None = None, stdout: BinaryIO | None = None) -> int:
    input_stream = stdin or cast(BufferedReader, sys.stdin.buffer)
    output_stream = stdout or cast(BufferedWriter, sys.stdout.buffer)
    writer = ProtocolWriter(output_stream)
    factory = AgentMessageFactory()
    stop_event = threading.Event()

    writer.write(factory.hello())

    runner_thread: threading.Thread | None = None
    try:
        preload_tesserocr_preserving_sigint_handler()
    except Exception as exc:
        logger.exception("ocr_preload_failed")
        writer.write(
            factory.status(
                state="degraded",
                capture_available=False,
                code="ocr_preload_failed",
                detail=str(exc),
            )
        )
    else:
        runner_thread = threading.Thread(
            name="zml-ocr-runner",
            target=_run_runner,
            kwargs={
                "writer": writer,
                "factory": factory,
                "stop_event": stop_event,
            },
            daemon=True,
        )
        runner_thread.start()

    try:
        for line in input_stream:
            try:
                command = decode_bridge_message(line)
            except OcrProtocolError:
                logger.warning("invalid_protocol_command", exc_info=True)
                continue

            if _handle_command(command, writer=writer, factory=factory, stop_event=stop_event):
                _join_runner(runner_thread)
                writer.write(
                    factory.command_ok(
                        command_id=command.command_id,
                        command_type="shutdown",
                    )
                )
                return 0
    finally:
        stop_event.set()
        _join_runner(runner_thread)

    return 0


def _run_runner(
    *,
    writer: ProtocolWriter,
    factory: AgentMessageFactory,
    stop_event: threading.Event,
) -> None:
    try:
        start_ocr_input(
            message_sink=writer.write,
            message_factory=factory,
            stop_event=stop_event,
        )
    except Exception as exc:
        logger.exception("ocr_runner_crashed")
        writer.write(
            factory.status(
                state="degraded",
                capture_available=False,
                code="ocr_runner_crashed",
                detail=str(exc),
            )
        )


def _handle_command(
    command: BridgeToAgentMessage,
    *,
    writer: ProtocolWriter,
    factory: AgentMessageFactory,
    stop_event: threading.Event,
) -> bool:
    match command.type:
        case "shutdown":
            stop_event.set()
            return True
        case "apply_config" | "capture_frame":
            writer.write(
                factory.command_error(
                    command_id=command.command_id,
                    command_type=command.type,
                    code="not_implemented",
                    message=f"{command.type} is scheduled for the config-sync migration step",
                    retryable=False,
                )
            )
            return False


def _join_runner(runner_thread: threading.Thread | None) -> None:
    if runner_thread is not None:
        runner_thread.join(timeout=5.0)
