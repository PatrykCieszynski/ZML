from __future__ import annotations

import logging
import queue
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from zml_ocr_protocol import (
    AgentToBridgeMessage,
    ApplyConfigCommand,
    ApplyConfigPayload,
    CommandResultMessage,
    FinderSignalMessage,
    HeartbeatMessage,
    HelloMessage,
    OcrProtocolError,
    PositionMessage,
    ShutdownCommand,
    ShutdownPayload,
    StatusMessage,
    decode_agent_message,
)
from zml_ocr_protocol.messages import AgentStatusState

from zml_game_bridge.runtime.ocr_agent.process_transport import (
    OcrAgentProcessConfig,
    OcrProcessTransport,
    StdioOcrProcessTransport,
)
from zml_game_bridge.runtime.supervisor import WorkerSupervisor

logger = logging.getLogger(__name__)

_OCR_WORKER_NAME = "ocr_worker"
_REQUIRED_CAPABILITIES = frozenset(
    {"position", "finder", "status", "heartbeat", "apply_config", "shutdown"}
)
_FATAL_AGENT_STATUS_CODES = frozenset({"ocr_preload_failed", "ocr_runner_crashed"})

MonotonicClock = Callable[[], float]
TransportFactory = Callable[[], OcrProcessTransport]
PositionMessageSink = Callable[[PositionMessage], None]
FinderMessageSink = Callable[[FinderSignalMessage], None]


class OcrAgentProcessError(RuntimeError):
    """The child process or its protocol stream became unusable."""


@dataclass(frozen=True, slots=True)
class RestartPolicy:
    delays_s: tuple[float, ...] = (0.5, 1.0, 2.0, 4.0)
    max_restarts_per_window: int = 4
    window_s: float = 60.0
    stable_reset_s: float = 30.0

    def __post_init__(self) -> None:
        if not self.delays_s or any(delay < 0 for delay in self.delays_s):
            raise ValueError("restart delays must contain non-negative values")
        if self.max_restarts_per_window < 1:
            raise ValueError("max_restarts_per_window must be positive")
        if self.window_s <= 0 or self.stable_reset_s <= 0:
            raise ValueError("restart windows must be positive")

    def delay_after_failure(
        self,
        *,
        failure_times: list[float],
        now: float,
        consecutive_failures: int,
    ) -> float:
        failure_times[:] = [value for value in failure_times if now - value < self.window_s]
        failure_times.append(now)
        if len(failure_times) > self.max_restarts_per_window:
            return max(0.0, self.window_s - (now - failure_times[0]))
        index = min(max(0, consecutive_failures - 1), len(self.delays_s) - 1)
        return self.delays_s[index]


@dataclass(frozen=True, slots=True)
class OcrAgentSupervisorConfig:
    enabled: bool
    process: OcrAgentProcessConfig
    desired_config: ApplyConfigPayload
    handshake_timeout_s: float = 5.0
    config_timeout_s: float = 10.0
    heartbeat_timeout_s: float = 8.0
    monitor_interval_s: float = 0.05
    restart: RestartPolicy = field(default_factory=RestartPolicy)


@dataclass(frozen=True, slots=True)
class _ProcessRunResult:
    error: BaseException | None
    uptime_s: float


class OcrAgentSupervisor:
    """Run OCR Agent as a restartable child while implementing OcrInputSource."""

    def __init__(
        self,
        *,
        config: OcrAgentSupervisorConfig,
        supervisor: WorkerSupervisor,
        position_message_sink: PositionMessageSink,
        finder_message_sink: FinderMessageSink,
        transport_factory: TransportFactory | None = None,
        monotonic: MonotonicClock | None = None,
    ) -> None:
        self._config = config
        self._supervisor = supervisor
        self._position_message_sink = position_message_sink
        self._finder_message_sink = finder_message_sink
        self._transport_factory = transport_factory or (
            lambda: StdioOcrProcessTransport(config.process)
        )
        self._monotonic = monotonic or time.monotonic

    @property
    def config(self) -> OcrAgentSupervisorConfig:
        return self._config

    def start(self, *, stop_event: threading.Event) -> None:
        if not self._config.enabled:
            return
        self._supervisor.start_thread(
            name=_OCR_WORKER_NAME,
            target=self._run,
            worker_kwargs={"stop_event": stop_event},
        )

    def stop(self) -> None:
        if self._config.enabled:
            self._supervisor.join_thread(_OCR_WORKER_NAME)

    def _run(self, *, stop_event: threading.Event) -> None:
        failure_times: list[float] = []
        consecutive_failures = 0
        restart_count = 0
        self._supervisor.update_details(
            _OCR_WORKER_NAME,
            transport="agent",
            process_state="starting",
            restart_count=0,
        )

        while not stop_event.is_set():
            result = self._run_process_once(
                stop_event=stop_event,
                restart_count=restart_count,
            )
            if stop_event.is_set() or result.error is None:
                break

            if result.uptime_s >= self._config.restart.stable_reset_s:
                consecutive_failures = 0
                failure_times.clear()
            consecutive_failures += 1
            restart_count += 1
            failure_at = self._monotonic()
            delay_s = self._config.restart.delay_after_failure(
                failure_times=failure_times,
                now=failure_at,
                consecutive_failures=consecutive_failures,
            )
            error_text = f"{type(result.error).__name__}: {result.error}"
            self._supervisor.update_details(
                _OCR_WORKER_NAME,
                process_state="restart_backoff",
                failure_kind="process",
                restart_count=restart_count,
                restart_delay_s=delay_s,
                last_process_error=error_text,
            )
            self._supervisor.mark_degraded(
                _OCR_WORKER_NAME,
                f"OCR Agent process failed; restart {restart_count} in {delay_s:.2f}s: {error_text}",
            )
            logger.warning(
                "ocr_agent_restart_scheduled restart_count=%s delay_s=%.2f error=%s",
                restart_count,
                delay_s,
                error_text,
            )
            stop_event.wait(delay_s)

        self._supervisor.update_details(
            _OCR_WORKER_NAME,
            process_state="stopped",
            pid=None,
            restart_count=restart_count,
        )

    def _run_process_once(
        self,
        *,
        stop_event: threading.Event,
        restart_count: int,
    ) -> _ProcessRunResult:
        transport = self._transport_factory()
        started_at = self._monotonic()
        try:
            transport.start()
        except Exception as exc:
            return _ProcessRunResult(
                error=OcrAgentProcessError(f"failed to start child: {exc}"),
                uptime_s=0.0,
            )

        self._supervisor.update_details(
            _OCR_WORKER_NAME,
            process_state="handshake",
            failure_kind=None,
            pid=transport.pid,
            restart_count=restart_count,
            desired_config_revision=self._config.desired_config.revision,
            applied_config_revision=None,
        )
        self._supervisor.mark_degraded(_OCR_WORKER_NAME, "OCR Agent handshake pending")

        failures: queue.Queue[BaseException] = queue.Queue()
        session = _ProtocolSession(
            position_message_sink=self._position_message_sink,
            finder_message_sink=self._finder_message_sink,
            supervisor=self._supervisor,
            monotonic=self._monotonic,
        )
        stdout_thread = threading.Thread(
            name="ocr-agent-stdout",
            target=_read_stdout,
            kwargs={"transport": transport, "session": session, "failures": failures},
            daemon=True,
        )
        stderr_thread = threading.Thread(
            name="ocr-agent-stderr",
            target=_drain_stderr,
            kwargs={"transport": transport},
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

        error: BaseException | None = None
        try:
            error = self._wait_for_handshake(
                transport=transport,
                session=session,
                failures=failures,
                stop_event=stop_event,
            )
            if error is None and not stop_event.is_set():
                error = self._apply_desired_config(
                    transport=transport,
                    session=session,
                    failures=failures,
                    stop_event=stop_event,
                )
            if error is None and not stop_event.is_set():
                error = self._monitor_process(
                    transport=transport,
                    session=session,
                    failures=failures,
                    stop_event=stop_event,
                )

            if stop_event.is_set():
                _stop_process_gracefully(transport)
                error = None
            elif error is not None:
                _force_stop_process(transport)
        finally:
            if transport.poll() is None:
                _force_stop_process(transport)
            stdout_thread.join(timeout=1.0)
            stderr_thread.join(timeout=1.0)

        return _ProcessRunResult(
            error=error,
            uptime_s=max(0.0, self._monotonic() - started_at),
        )

    def _wait_for_handshake(
        self,
        *,
        transport: OcrProcessTransport,
        session: _ProtocolSession,
        failures: queue.Queue[BaseException],
        stop_event: threading.Event,
    ) -> BaseException | None:
        deadline = self._monotonic() + self._config.handshake_timeout_s
        while not stop_event.is_set():
            failure = _take_failure(failures)
            if failure is not None:
                return failure
            exit_code = transport.poll()
            if exit_code is not None:
                return OcrAgentProcessError(f"child exited before hello with code {exit_code}")
            if session.handshake_complete.is_set():
                return None
            if self._monotonic() >= deadline:
                return OcrAgentProcessError("hello handshake timed out")
            stop_event.wait(self._config.monitor_interval_s)
        return None

    def _apply_desired_config(
        self,
        *,
        transport: OcrProcessTransport,
        session: _ProtocolSession,
        failures: queue.Queue[BaseException],
        stop_event: threading.Event,
    ) -> BaseException | None:
        command_id = uuid.uuid4().hex
        revision = self._config.desired_config.revision
        session.expect_config(command_id=command_id, revision=revision)
        self._supervisor.update_details(
            _OCR_WORKER_NAME,
            process_state="configuring",
            desired_config_revision=revision,
        )
        try:
            transport.send(
                ApplyConfigCommand(
                    protocol_version=1,
                    type="apply_config",
                    command_id=command_id,
                    sent_ts_ms=time.time_ns() // 1_000_000,
                    payload=self._config.desired_config,
                )
            )
        except Exception as exc:
            return OcrAgentProcessError(f"failed to send apply_config: {exc}")

        deadline = self._monotonic() + self._config.config_timeout_s
        while not stop_event.is_set():
            failure = _take_failure(failures)
            if failure is not None:
                return failure
            exit_code = transport.poll()
            if exit_code is not None:
                return OcrAgentProcessError(
                    f"child exited while applying config with code {exit_code}"
                )
            if session.config_complete.is_set():
                return session.config_error
            if self._monotonic() >= deadline:
                return OcrAgentProcessError(f"apply_config revision {revision} timed out")
            stop_event.wait(self._config.monitor_interval_s)
        return None

    def _monitor_process(
        self,
        *,
        transport: OcrProcessTransport,
        session: _ProtocolSession,
        failures: queue.Queue[BaseException],
        stop_event: threading.Event,
    ) -> BaseException | None:
        while not stop_event.is_set():
            failure = _take_failure(failures)
            if failure is not None:
                return failure
            exit_code = transport.poll()
            if exit_code is not None:
                return OcrAgentProcessError(f"child exited unexpectedly with code {exit_code}")
            heartbeat_age_s = session.heartbeat_age_s()
            if heartbeat_age_s > self._config.heartbeat_timeout_s:
                return OcrAgentProcessError(f"heartbeat timed out after {heartbeat_age_s:.2f}s")
            stop_event.wait(self._config.monitor_interval_s)
        return None


class _ProtocolSession:
    def __init__(
        self,
        *,
        position_message_sink: PositionMessageSink,
        finder_message_sink: FinderMessageSink,
        supervisor: WorkerSupervisor,
        monotonic: MonotonicClock,
    ) -> None:
        self._position_message_sink = position_message_sink
        self._finder_message_sink = finder_message_sink
        self._supervisor = supervisor
        self._monotonic = monotonic
        self._lock = threading.Lock()
        self._hello_received = False
        self._last_sequence_id = -1
        self._last_heartbeat_at = monotonic()
        self._expected_config_command_id: str | None = None
        self._expected_config_revision: int | None = None
        self.config_error: BaseException | None = None
        self.handshake_complete = threading.Event()
        self.config_complete = threading.Event()

    def expect_config(self, *, command_id: str, revision: int) -> None:
        with self._lock:
            if not self._hello_received:
                raise OcrAgentProcessError("cannot configure OCR Agent before hello")
            if self._expected_config_command_id is not None:
                raise OcrAgentProcessError("OCR Agent config command is already pending")
            self._expected_config_command_id = command_id
            self._expected_config_revision = revision

    def handle(self, message: AgentToBridgeMessage) -> None:
        with self._lock:
            if not self._hello_received:
                if not isinstance(message, HelloMessage):
                    raise OcrAgentProcessError("first OCR Agent message must be hello")
                missing = _REQUIRED_CAPABILITIES.difference(message.payload.capabilities)
                if missing:
                    missing_text = ", ".join(sorted(missing))
                    raise OcrAgentProcessError(
                        f"OCR Agent is missing required capabilities: {missing_text}"
                    )
                self._hello_received = True
                self._last_sequence_id = message.sequence_id
                self._last_heartbeat_at = self._monotonic()
                self._supervisor.update_details(
                    _OCR_WORKER_NAME,
                    process_state="connected",
                    protocol_version=message.protocol_version,
                    agent_version=message.payload.agent_version,
                    agent_pid=message.payload.pid,
                    last_sequence_id=message.sequence_id,
                )
                self.handshake_complete.set()
                return

            if isinstance(message, HelloMessage):
                raise OcrAgentProcessError("OCR Agent emitted duplicate hello")
            if message.sequence_id <= self._last_sequence_id:
                raise OcrAgentProcessError(
                    "OCR Agent sequence_id must increase monotonically "
                    f"({message.sequence_id} <= {self._last_sequence_id})"
                )
            self._last_sequence_id = message.sequence_id
            self._supervisor.update_details(
                _OCR_WORKER_NAME,
                last_sequence_id=message.sequence_id,
            )

            if isinstance(message, PositionMessage):
                self._require_configured_observations()
                self._position_message_sink(message)
                return
            if isinstance(message, FinderSignalMessage):
                self._require_configured_observations()
                self._finder_message_sink(message)
                return
            if isinstance(message, StatusMessage):
                self._observe_applied_revision(message.payload.applied_revision)
                self._apply_agent_state(
                    state=message.payload.state,
                    detail=message.payload.detail,
                    code=message.payload.code,
                )
                return
            if isinstance(message, HeartbeatMessage):
                self._last_heartbeat_at = self._monotonic()
                self._observe_applied_revision(message.payload.applied_revision)
                self._supervisor.update_details(
                    _OCR_WORKER_NAME,
                    last_heartbeat_ts_ms=message.emitted_ts_ms,
                )
                self._apply_agent_state(
                    state=message.payload.state,
                    detail=None,
                    code=None,
                )
                return
            self._handle_command_result(message)
            return

    def heartbeat_age_s(self) -> float:
        with self._lock:
            return max(0.0, self._monotonic() - self._last_heartbeat_at)

    def _handle_command_result(self, message: CommandResultMessage) -> None:
        command_id = self._expected_config_command_id
        revision = self._expected_config_revision
        if command_id is None or revision is None:
            raise OcrAgentProcessError("OCR Agent emitted an unexpected command_result")
        payload = message.payload
        if payload.command_id != command_id or payload.command_type != "apply_config":
            raise OcrAgentProcessError("OCR Agent returned command_result for another command")
        if payload.status == "error":
            error = payload.error
            detail = "unknown error" if error is None else f"{error.code}: {error.message}"
            self.config_error = OcrAgentProcessError(
                f"OCR Agent rejected config revision {revision}: {detail}"
            )
            self.config_complete.set()
            return
        if payload.applied_revision != revision:
            raise OcrAgentProcessError(
                "OCR Agent acknowledged unexpected config revision "
                f"{payload.applied_revision}; expected {revision}"
            )
        self._supervisor.update_details(
            _OCR_WORKER_NAME,
            process_state="configured",
            applied_config_revision=revision,
        )
        self.config_complete.set()

    def _require_configured_observations(self) -> None:
        if not self.config_complete.is_set() or self.config_error is not None:
            raise OcrAgentProcessError(
                "OCR Agent emitted an observation before apply_config completed"
            )

    def _observe_applied_revision(self, revision: int | None) -> None:
        self._supervisor.update_details(
            _OCR_WORKER_NAME,
            applied_config_revision=revision,
        )

    def _apply_agent_state(
        self,
        *,
        state: AgentStatusState,
        detail: str | None,
        code: str | None,
    ) -> None:
        if code in _FATAL_AGENT_STATUS_CODES:
            message = detail or f"OCR Agent reported fatal status {code}"
            self._supervisor.update_details(
                _OCR_WORKER_NAME,
                process_state="agent_failed",
                failure_kind="process",
                agent_status_code=code,
            )
            raise OcrAgentProcessError(message)
        if state == "running":
            self._supervisor.update_details(
                _OCR_WORKER_NAME,
                process_state="running",
                failure_kind=None,
                agent_status_code=code,
            )
            self._supervisor.mark_running(_OCR_WORKER_NAME)
            return
        if state == "waiting_for_window":
            message = detail or "Entropia Universe window is unavailable"
            self._supervisor.update_details(
                _OCR_WORKER_NAME,
                process_state="window_unavailable",
                failure_kind="capture",
                agent_status_code=code,
            )
            self._supervisor.mark_degraded(_OCR_WORKER_NAME, message)
            return

        message = detail or "OCR Agent reported degraded state"
        self._supervisor.update_details(
            _OCR_WORKER_NAME,
            process_state="degraded",
            failure_kind="agent",
            agent_status_code=code,
        )
        self._supervisor.mark_degraded(_OCR_WORKER_NAME, message)


def _read_stdout(
    *,
    transport: OcrProcessTransport,
    session: _ProtocolSession,
    failures: queue.Queue[BaseException],
) -> None:
    try:
        while True:
            line = transport.read_stdout_line()
            if not line:
                failures.put(OcrAgentProcessError("OCR Agent stdout closed"))
                return
            try:
                message = decode_agent_message(line)
                session.handle(message)
            except (OcrProtocolError, OcrAgentProcessError, ValueError) as exc:
                failures.put(exc)
                return
    except Exception as exc:
        failures.put(OcrAgentProcessError(f"stdout reader failed: {exc}"))


def _drain_stderr(*, transport: OcrProcessTransport) -> None:
    try:
        while True:
            line = transport.read_stderr_line()
            if not line:
                return
            logger.info(
                "ocr_agent_stderr line=%s",
                line.decode("utf-8", errors="replace").rstrip(),
            )
    except Exception:
        logger.warning("ocr_agent_stderr_reader_failed", exc_info=True)


def _take_failure(failures: queue.Queue[BaseException]) -> BaseException | None:
    try:
        return failures.get_nowait()
    except queue.Empty:
        return None


def _stop_process_gracefully(transport: OcrProcessTransport) -> None:
    try:
        transport.send(
            ShutdownCommand(
                protocol_version=1,
                type="shutdown",
                command_id=uuid.uuid4().hex,
                sent_ts_ms=time.time_ns() // 1_000_000,
                payload=ShutdownPayload(reason="backend_shutdown"),
            )
        )
    except Exception:
        logger.debug("ocr_agent_shutdown_command_failed", exc_info=True)
    try:
        transport.close_stdin()
    except Exception:
        logger.debug("ocr_agent_shutdown_stdin_close_failed", exc_info=True)
    if transport.wait(timeout_s=3.0) is not None:
        return
    _force_stop_process(transport)


def _force_stop_process(transport: OcrProcessTransport) -> None:
    try:
        transport.close_stdin()
    except Exception:
        logger.debug("ocr_agent_close_stdin_failed", exc_info=True)
    if transport.wait(timeout_s=0.5) is not None:
        return
    try:
        transport.terminate()
    except Exception:
        logger.debug("ocr_agent_terminate_failed", exc_info=True)
    if transport.wait(timeout_s=1.0) is not None:
        return
    try:
        transport.kill()
    except Exception:
        logger.warning("ocr_agent_kill_failed", exc_info=True)
    transport.wait(timeout_s=1.0)
