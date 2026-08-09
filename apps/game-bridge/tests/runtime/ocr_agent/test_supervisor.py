from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from zml_ocr_protocol import (
    AgentToBridgeMessage,
    ApplyConfigCommand,
    CommandResultMessage,
    FinderSignalMessage,
    HeartbeatMessage,
    HelloMessage,
    PositionMessage,
    encode_message,
)
from zml_ocr_protocol.messages import (
    AgentStatusState,
    CommandResultPayload,
    FinderNoResourcesPayload,
    HeartbeatPayload,
    HelloPayload,
    PositionObservationPayload,
    StatusMessage,
    StatusPayload,
    WorldPositionPayload,
)

from zml_game_bridge.application.mining.signals.finder import FinderNoResourcesSignal
from zml_game_bridge.application.position.model import PositionSnapshot
from zml_game_bridge.events.base import SignalBase
from zml_game_bridge.inputs.ocr_agent.config import build_desired_ocr_config
from zml_game_bridge.inputs.ocr_agent.message_mapper import OcrAgentMessageMapper
from zml_game_bridge.runtime.ocr_agent.process_transport import (
    OcrAgentProcessConfig,
    OcrProcessTransport,
)
from zml_game_bridge.runtime.ocr_agent.supervisor import (
    OcrAgentProcessError,
    OcrAgentSupervisor,
    OcrAgentSupervisorConfig,
    RestartPolicy,
    _ProtocolSession,
)
from zml_game_bridge.runtime.supervisor import WorkerSupervisor
from zml_game_bridge.settings import Settings


def test_protocol_session_requires_hello_before_observations() -> None:
    session, _, _, _ = _session()

    with pytest.raises(OcrAgentProcessError, match="first OCR Agent message must be hello"):
        session.handle(_position(sequence_id=0))


def test_protocol_session_maps_observations_and_distinguishes_window_health() -> None:
    session, supervisor, positions, signals = _session(clock_ms=lambda: 2_000)

    _configure_session(session)
    session.handle(_status_waiting(sequence_id=2))

    worker = _worker_health(supervisor)
    assert worker["state"] == "degraded"
    assert worker["last_error"] == "window missing"
    assert worker["details"]["process_state"] == "window_unavailable"
    assert worker["details"]["failure_kind"] == "capture"

    session.handle(_position(sequence_id=3))
    session.handle(_finder(sequence_id=4))
    session.handle(_heartbeat(sequence_id=5, state="running", capture_available=True))

    assert positions[0].observed_ts_ms == 1_000
    assert positions[0].received_ts_ms == 2_000
    assert positions[0].position.x == 58_000
    assert signals == [
        FinderNoResourcesSignal(
            ts_ms=1_500,
            raw_status_text="No resources found",
            roi_name="finder",
        )
    ]
    worker = _worker_health(supervisor)
    assert worker["state"] == "running"
    assert worker["details"]["process_state"] == "running"
    assert worker["details"]["failure_kind"] is None


def test_protocol_session_rejects_fatal_agent_status_and_non_monotonic_sequence() -> None:
    session, _, _, _ = _session()
    _configure_session(session)

    with pytest.raises(OcrAgentProcessError, match="tesserocr unavailable"):
        session.handle(
            StatusMessage(
                protocol_version=1,
                type="status",
                message_id="f" * 32,
                sequence_id=2,
                emitted_ts_ms=1_001,
                payload=StatusPayload(
                    state="degraded",
                    capture_available=False,
                    applied_revision=None,
                    code="ocr_preload_failed",
                    detail="tesserocr unavailable",
                ),
            )
        )

    session, _, _, _ = _session()
    _configure_session(session)
    session.handle(_heartbeat(sequence_id=3, state="running", capture_available=True))
    with pytest.raises(OcrAgentProcessError, match="increase monotonically"):
        session.handle(_position(sequence_id=2))


@pytest.mark.timeout(2)
def test_supervisor_restarts_agent_and_accepts_position_and_finder_after_restart(
    tmp_path: Path,
) -> None:
    stop_event = threading.Event()
    positions: list[PositionSnapshot] = []
    signals: list[SignalBase] = []
    transports = [
        _FakeTransport([_hello()], exit_after_messages=True, pid=100),
        _FakeTransport(
            [
                _hello(pid=101),
                _status_waiting(sequence_id=2),
                _heartbeat(sequence_id=3, state="waiting_for_window", capture_available=False),
                _position(sequence_id=4),
                _finder(sequence_id=5),
            ],
            exit_after_messages=False,
            pid=101,
        ),
    ]
    created: list[_FakeTransport] = []

    def transport_factory() -> OcrProcessTransport:
        transport = transports[len(created)]
        created.append(transport)
        return transport

    def signal_sink(signal: SignalBase) -> None:
        signals.append(signal)
        stop_event.set()

    supervisor = WorkerSupervisor()
    supervisor.register("ocr_worker", enabled=True)
    mapper = OcrAgentMessageMapper(
        position_sink=positions.append,
        signal_sink=signal_sink,
    )
    source = OcrAgentSupervisor(
        config=OcrAgentSupervisorConfig(
            enabled=True,
            process=OcrAgentProcessConfig(command=("fake-agent",), environment={}),
            desired_config=build_desired_ocr_config(
                Settings(ocr_profile_path=tmp_path / "ocr-profile.json")
            ),
            handshake_timeout_s=0.5,
            heartbeat_timeout_s=0.5,
            monitor_interval_s=0.001,
            restart=RestartPolicy(delays_s=(0.0,), stable_reset_s=1.0),
        ),
        supervisor=supervisor,
        position_message_sink=mapper.map_position,
        finder_message_sink=mapper.map_finder,
        transport_factory=transport_factory,
    )

    source.start(stop_event=stop_event)
    assert stop_event.wait(timeout=1.0)
    source.stop()

    assert len(created) == 2
    assert created[0].pid == 100
    assert created[1].pid == 101
    assert len(positions) == 1
    assert positions[0].position.x == 58_000
    assert isinstance(signals[0], FinderNoResourcesSignal)
    assert created[1].sent_shutdown
    worker = _worker_health(supervisor)
    assert worker["details"]["restart_count"] == 1
    assert worker["details"]["failure_kind"] == "capture"


def _session(
    *,
    clock_ms: Callable[[], int] | None = None,
) -> tuple[_ProtocolSession, WorkerSupervisor, list[PositionSnapshot], list[SignalBase]]:
    positions: list[PositionSnapshot] = []
    signals: list[SignalBase] = []
    supervisor = WorkerSupervisor()
    supervisor.register("ocr_worker", enabled=True)
    mapper = OcrAgentMessageMapper(
        position_sink=positions.append,
        signal_sink=signals.append,
        clock_ms=clock_ms,
    )
    session = _ProtocolSession(
        position_message_sink=mapper.map_position,
        finder_message_sink=mapper.map_finder,
        supervisor=supervisor,
        monotonic=time.monotonic,
    )
    return session, supervisor, positions, signals


def _worker_health(supervisor: WorkerSupervisor) -> dict[str, object]:
    workers = cast(dict[str, dict[str, object]], supervisor.health()["workers"])
    return workers["ocr_worker"]


def _configure_session(session: _ProtocolSession) -> None:
    command_id = "0" * 32
    session.handle(_hello())
    session.expect_config(command_id=command_id, revision=1)
    session.handle(_config_result(command_id=command_id, sequence_id=1))


def _config_result(*, command_id: str, sequence_id: int) -> CommandResultMessage:
    return CommandResultMessage(
        protocol_version=1,
        type="command_result",
        message_id="f" * 32,
        sequence_id=sequence_id,
        emitted_ts_ms=1_001,
        payload=CommandResultPayload(
            command_id=command_id,
            command_type="apply_config",
            status="ok",
            applied_revision=1,
            capture=None,
            error=None,
        ),
    )


def _hello(*, pid: int = 123) -> HelloMessage:
    return HelloMessage(
        protocol_version=1,
        type="hello",
        message_id="a" * 32,
        sequence_id=0,
        emitted_ts_ms=1_000,
        payload=HelloPayload(
            agent_version="0.1.0",
            pid=pid,
            started_ts_ms=999,
            capabilities=[
                "stdio",
                "position",
                "finder",
                "status",
                "heartbeat",
                "apply_config",
                "shutdown",
            ],
        ),
    )


def _position(*, sequence_id: int) -> PositionMessage:
    return PositionMessage(
        protocol_version=1,
        type="position",
        message_id="b" * 32,
        sequence_id=sequence_id,
        emitted_ts_ms=1_001,
        observed_ts_ms=1_000,
        payload=PositionObservationPayload(
            position=WorldPositionPayload(
                planet_name="Calypso",
                x=58_000,
                y=84_000,
                z=None,
            ),
            confidence=None,
            roi_name="compass",
        ),
    )


def _finder(*, sequence_id: int) -> FinderSignalMessage:
    return FinderSignalMessage(
        protocol_version=1,
        type="finder_signal",
        message_id="c" * 32,
        sequence_id=sequence_id,
        emitted_ts_ms=1_501,
        observed_ts_ms=1_500,
        payload=FinderNoResourcesPayload(
            kind="finder_no_resources",
            raw_status_text="No resources found",
            roi_name="finder",
            debug={},
        ),
    )


def _status_waiting(*, sequence_id: int) -> StatusMessage:
    return StatusMessage(
        protocol_version=1,
        type="status",
        message_id="d" * 32,
        sequence_id=sequence_id,
        emitted_ts_ms=1_002,
        payload=StatusPayload(
            state="waiting_for_window",
            capture_available=False,
            applied_revision=1,
            code="window_unavailable",
            detail="window missing",
        ),
    )


def _heartbeat(
    *,
    sequence_id: int,
    state: AgentStatusState,
    capture_available: bool,
) -> HeartbeatMessage:
    return HeartbeatMessage(
        protocol_version=1,
        type="heartbeat",
        message_id="e" * 32,
        sequence_id=sequence_id,
        emitted_ts_ms=1_003,
        payload=HeartbeatPayload(
            state=state,
            capture_available=capture_available,
            applied_revision=1,
        ),
    )


_EOF = object()


class _FakeTransport:
    def __init__(
        self,
        messages: list[AgentToBridgeMessage],
        *,
        exit_after_messages: bool,
        pid: int,
    ) -> None:
        self.pid = pid
        self._messages = messages
        self._exit_after_messages = exit_after_messages
        self._stdout: queue.Queue[bytes | object] = queue.Queue()
        self._stderr: queue.Queue[bytes | object] = queue.Queue()
        self._exit_event = threading.Event()
        self._returncode: int | None = None
        self.sent_shutdown = False

    def start(self) -> None:
        self._stdout.put(encode_message(self._messages[0]))

    def read_stdout_line(self) -> bytes:
        item = self._stdout.get(timeout=1.0)
        if item is _EOF:
            self._exit(1)
            return b""
        return cast(bytes, item)

    def read_stderr_line(self) -> bytes:
        item = self._stderr.get(timeout=1.0)
        return b"" if item is _EOF else cast(bytes, item)

    def send(self, message: object) -> None:
        if isinstance(message, ApplyConfigCommand):
            self._stdout.put(
                encode_message(
                    CommandResultMessage(
                        protocol_version=1,
                        type="command_result",
                        message_id="f" * 32,
                        sequence_id=1,
                        emitted_ts_ms=1_004,
                        payload=CommandResultPayload(
                            command_id=message.command_id,
                            command_type="apply_config",
                            status="ok",
                            applied_revision=message.payload.revision,
                            capture=None,
                            error=None,
                        ),
                    )
                )
            )
            for observation in self._messages[1:]:
                self._stdout.put(encode_message(observation))
            if self._exit_after_messages:
                self._stdout.put(_EOF)
            return
        self.sent_shutdown = getattr(message, "type", None) == "shutdown"
        self._exit(0)

    def poll(self) -> int | None:
        return self._returncode

    def wait(self, *, timeout_s: float) -> int | None:
        self._exit_event.wait(timeout_s)
        return self._returncode

    def close_stdin(self) -> None:
        pass

    def terminate(self) -> None:
        self._exit(-15)

    def kill(self) -> None:
        self._exit(-9)

    def _exit(self, returncode: int) -> None:
        if self._returncode is not None:
            return
        self._returncode = returncode
        self._exit_event.set()
        self._stdout.put(_EOF)
        self._stderr.put(_EOF)
