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
from zml_ocr_protocol.messages import (
    AgentStatusState,
    AgentToBridgeMessage,
    ApplyConfigCommand,
    BridgeToAgentMessage,
    StatusMessage,
)

from zml_ocr_worker.config import AppliedOcrConfig, applied_ocr_config
from zml_ocr_worker.runtime.message_factory import AgentMessageFactory
from zml_ocr_worker.runtime.runner import start_ocr_input
from zml_ocr_worker.runtime.tesserocr import preload_tesserocr_preserving_sigint_handler

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

    def mark_configuring(self) -> None:
        with self._lock:
            self._state = "degraded"
            self._capture_available = False


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


class OcrRunnerController:
    def __init__(
        self,
        *,
        writer: ProtocolWriter,
        factory: AgentMessageFactory,
        runtime_state: AgentRuntimeState,
    ) -> None:
        self._writer = writer
        self._factory = factory
        self._runtime_state = runtime_state
        self._thread: threading.Thread | None = None
        self._stop_event: threading.Event | None = None
        self._applied: AppliedOcrConfig | None = None
        self._pending: tuple[threading.Thread, threading.Event, AppliedOcrConfig] | None = None

    def apply(self, command: ApplyConfigCommand) -> tuple[bool, str | None, str | None]:
        candidate = applied_ocr_config(command.payload)
        current = self._applied
        if current is not None and candidate.revision < current.revision:
            return (
                False,
                "stale_config_revision",
                (
                    f"revision {candidate.revision} is older than applied revision {current.revision}"
                ),
            )
        if current is not None and candidate.revision == current.revision:
            if candidate == current:
                return True, None, None
            return (
                False,
                "config_revision_conflict",
                (f"revision {candidate.revision} was already applied with different values"),
            )

        self._runtime_state.mark_configuring()
        if not self.stop(timeout_s=5.0):
            return False, "ocr_runner_stop_timeout", "previous OCR runner did not stop"

        runner_stop_event = threading.Event()
        runner_thread = threading.Thread(
            name="zml-ocr-runner",
            target=_run_runner,
            kwargs={
                "writer": self._writer,
                "factory": self._factory,
                "stop_event": runner_stop_event,
                "config": candidate,
            },
            daemon=True,
        )
        self._pending = (runner_thread, runner_stop_event, candidate)
        return True, None, None

    def start_pending(self) -> None:
        pending = self._pending
        if pending is None:
            return
        runner_thread, runner_stop_event, candidate = pending
        self._factory.set_applied_revision(candidate.revision)
        self._applied = candidate
        self._stop_event = runner_stop_event
        self._thread = runner_thread
        self._pending = None
        runner_thread.start()

    def stop(self, *, timeout_s: float) -> bool:
        stop_event = self._stop_event
        thread = self._thread
        if stop_event is None or thread is None:
            return True
        stop_event.set()
        thread.join(timeout=timeout_s)
        if thread.is_alive():
            return False
        self._stop_event = None
        self._thread = None
        return True


def run_stdio(*, stdin: BinaryIO | None = None, stdout: BinaryIO | None = None) -> int:
    input_stream = stdin or cast(BufferedReader, sys.stdin.buffer)
    output_stream = stdout or cast(BufferedWriter, sys.stdout.buffer)
    runtime_state = AgentRuntimeState()
    writer = ProtocolWriter(output_stream, runtime_state=runtime_state)
    factory = AgentMessageFactory()
    stop_event = threading.Event()
    runner = OcrRunnerController(
        writer=writer,
        factory=factory,
        runtime_state=runtime_state,
    )

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
        stop_event.set()
        heartbeat_thread.join(timeout=1.0)
        return 1

    try:
        for line in input_stream:
            try:
                command = decode_bridge_message(line)
            except OcrProtocolError:
                logger.warning("invalid_protocol_command", exc_info=True)
                continue

            if _handle_command(
                command,
                writer=writer,
                factory=factory,
                runner=runner,
                stop_event=stop_event,
            ):
                runner.stop(timeout_s=5.0)
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
        runner.stop(timeout_s=5.0)
        heartbeat_thread.join(timeout=1.0)

    return 0


def _run_runner(
    *,
    writer: ProtocolWriter,
    factory: AgentMessageFactory,
    stop_event: threading.Event,
    config: AppliedOcrConfig,
) -> None:
    try:
        start_ocr_input(
            message_sink=writer.write,
            message_factory=factory,
            stop_event=stop_event,
            target_hz=config.capture_hz,
            finder_debug_logging=config.finder_debug_logging,
            finder_recording_modes=config.finder_recording_modes,
            finder_recording_dir=config.finder_recording_dir,
            finder_recording_interval_s=config.finder_recording_interval_s,
            finder_recording_max_samples=config.finder_recording_max_samples,
            finder_presence_check_enabled=config.finder_presence_check_enabled,
            position_roi_snapshot_enabled=config.position_roi_snapshot_enabled,
            position_roi_snapshot_dir=config.position_roi_snapshot_dir,
            position_roi_snapshot_interval_s=config.position_roi_snapshot_interval_s,
            position_roi_snapshot_max_samples=config.position_roi_snapshot_max_samples,
            ocr_profiling_enabled=config.ocr_profiling_enabled,
            ocr_profiling_interval_s=config.ocr_profiling_interval_s,
            roi_profile=config.roi_profile,
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
    runner: OcrRunnerController,
    stop_event: threading.Event,
) -> bool:
    match command.type:
        case "shutdown":
            stop_event.set()
            return True
        case "apply_config":
            ok, code, error = runner.apply(command)
            if ok:
                writer.write(
                    factory.command_applied(
                        command_id=command.command_id,
                        revision=command.payload.revision,
                    )
                )
                runner.start_pending()
                return False
            writer.write(
                factory.command_error(
                    command_id=command.command_id,
                    command_type="apply_config",
                    code=cast(str, code),
                    message=cast(str, error),
                    retryable=code == "ocr_runner_stop_timeout",
                )
            )
            return False
        case "capture_frame":
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
