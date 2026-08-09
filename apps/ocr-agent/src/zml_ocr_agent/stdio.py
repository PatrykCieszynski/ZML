from __future__ import annotations

import logging
import os
import sys
import threading
from io import BufferedReader, BufferedWriter
from pathlib import Path
from typing import BinaryIO, cast

from zml_ocr_protocol import (
    OcrProtocolError,
    decode_bridge_message,
    encode_message,
)
from zml_ocr_protocol.messages import (
    AgentStatusState,
    AgentToBridgeMessage,
    BridgeToAgentMessage,
    StatusMessage,
)

from zml_ocr_agent.message_factory import AgentMessageFactory
from zml_ocr_agent.runner import start_ocr_input
from zml_ocr_agent.tesserocr_runtime import preload_tesserocr_preserving_sigint_handler

logger = logging.getLogger(__name__)

_HEARTBEAT_INTERVAL_S = 2.0


class AgentRuntimeState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: AgentStatusState = "degraded"
        self._capture_available = False

    def observe(self, message: AgentToBridgeMessage) -> None:
        if not isinstance(message, StatusMessage):
            return
        with self._lock:
            self._state = message.payload.state
            self._capture_available = message.payload.capture_available

    def snapshot(self) -> tuple[AgentStatusState, bool]:
        with self._lock:
            return self._state, self._capture_available


class ProtocolWriter:
    def __init__(self, output: BinaryIO, *, runtime_state: AgentRuntimeState) -> None:
        self._output = output
        self._runtime_state = runtime_state
        self._lock = threading.Lock()
        self._next_sequence_id = 0

    def write(self, message: AgentToBridgeMessage) -> None:
        with self._lock:
            wire_message = message.model_copy(update={"sequence_id": self._next_sequence_id})
            self._next_sequence_id += 1
            self._runtime_state.observe(wire_message)
            encoded = encode_message(wire_message)
            self._output.write(encoded)
            self._output.flush()


def run_stdio(*, stdin: BinaryIO | None = None, stdout: BinaryIO | None = None) -> int:
    input_stream = stdin or cast(BufferedReader, sys.stdin.buffer)
    output_stream = stdout or cast(BufferedWriter, sys.stdout.buffer)
    runtime_state = AgentRuntimeState()
    writer = ProtocolWriter(output_stream, runtime_state=runtime_state)
    factory = AgentMessageFactory()
    stop_event = threading.Event()

    writer.write(factory.hello())
    heartbeat_thread = threading.Thread(
        name="zml-ocr-heartbeat",
        target=_run_heartbeat,
        kwargs={
            "writer": writer,
            "factory": factory,
            "runtime_state": runtime_state,
            "stop_event": stop_event,
        },
        daemon=True,
    )
    heartbeat_thread.start()

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
                "roi_profile_path": _env_path("ZML_OCR_PROFILE_PATH"),
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
                heartbeat_thread.join(timeout=1.0)
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
        heartbeat_thread.join(timeout=1.0)

    return 0


def _run_runner(
    *,
    writer: ProtocolWriter,
    factory: AgentMessageFactory,
    stop_event: threading.Event,
    roi_profile_path: Path | None,
) -> None:
    try:
        start_ocr_input(
            message_sink=writer.write,
            message_factory=factory,
            stop_event=stop_event,
            roi_profile_path=roi_profile_path,
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


def _run_heartbeat(
    *,
    writer: ProtocolWriter,
    factory: AgentMessageFactory,
    runtime_state: AgentRuntimeState,
    stop_event: threading.Event,
) -> None:
    while not stop_event.wait(_HEARTBEAT_INTERVAL_S):
        state, capture_available = runtime_state.snapshot()
        writer.write(
            factory.heartbeat(
                state=state,
                capture_available=capture_available,
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


def _env_path(name: str) -> Path | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    return Path(value)
