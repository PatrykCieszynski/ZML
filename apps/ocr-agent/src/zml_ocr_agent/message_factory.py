from __future__ import annotations

import os
import threading
import time
import uuid
from collections.abc import Callable
from typing import Literal

from zml_ocr_protocol.messages import (
    PROTOCOL_VERSION,
    AgentStatusState,
    CommandResultMessage,
    CommandResultPayload,
    CommandType,
    FinderHitHintPayload,
    FinderModeInvalidatedPayload,
    FinderModesChangedPayload,
    FinderNoResourcesPayload,
    FinderObservationPayload,
    FinderSignalMessage,
    FinderUnitsChangedPayload,
    HelloMessage,
    HelloPayload,
    PositionMessage,
    PositionObservationPayload,
    ProbeFiredPayload,
    ProtocolFailurePayload,
    StatusMessage,
    StatusPayload,
    WorldPositionPayload,
)

from zml_ocr_agent import __version__
from zml_ocr_agent.pipelines.mining_finder.model import MiningFinderSignal
from zml_ocr_agent.pipelines.position.model import OcrPosition

ClockMs = Callable[[], int]
MessageIdFactory = Callable[[], str]


class AgentMessageFactory:
    """Create ordered wire messages safely from the runner and command loop."""

    def __init__(
        self,
        *,
        clock_ms: ClockMs | None = None,
        message_id_factory: MessageIdFactory | None = None,
        agent_version: str = __version__,
        pid: int | None = None,
    ) -> None:
        self._clock_ms = clock_ms or _now_ms
        self._message_id_factory = message_id_factory or _new_message_id
        self._agent_version = agent_version
        self._pid = pid or os.getpid()
        self._started_ts_ms = self._clock_ms()
        self._sequence_id = -1
        self._lock = threading.Lock()

    def hello(self) -> HelloMessage:
        message_id, sequence_id, emitted_ts_ms = self._metadata()
        return HelloMessage(
            protocol_version=PROTOCOL_VERSION,
            type="hello",
            message_id=message_id,
            sequence_id=sequence_id,
            emitted_ts_ms=emitted_ts_ms,
            payload=HelloPayload(
                agent_version=self._agent_version,
                pid=self._pid,
                started_ts_ms=self._started_ts_ms,
                capabilities=["stdio", "position", "finder", "status"],
            ),
        )

    def position(
        self,
        observation: OcrPosition,
        *,
        roi_name: str,
        confidence: float | None = None,
    ) -> PositionMessage:
        message_id, sequence_id, emitted_ts_ms = self._metadata()
        position = observation.position
        return PositionMessage(
            protocol_version=PROTOCOL_VERSION,
            type="position",
            message_id=message_id,
            sequence_id=sequence_id,
            emitted_ts_ms=emitted_ts_ms,
            observed_ts_ms=observation.ts_ms,
            payload=PositionObservationPayload(
                position=WorldPositionPayload(
                    planet_name=position.planet_name,
                    x=position.x,
                    y=position.y,
                    z=position.z,
                ),
                confidence=confidence,
                roi_name=roi_name,
            ),
        )

    def finder(self, signal: MiningFinderSignal, *, roi_name: str) -> FinderSignalMessage:
        message_id, sequence_id, emitted_ts_ms = self._metadata()
        return FinderSignalMessage(
            protocol_version=PROTOCOL_VERSION,
            type="finder_signal",
            message_id=message_id,
            sequence_id=sequence_id,
            emitted_ts_ms=emitted_ts_ms,
            observed_ts_ms=signal.ts_ms,
            payload=_finder_payload(signal, roi_name=roi_name),
        )

    def status(
        self,
        *,
        state: AgentStatusState,
        capture_available: bool,
        code: str | None = None,
        detail: str | None = None,
    ) -> StatusMessage:
        message_id, sequence_id, emitted_ts_ms = self._metadata()
        return StatusMessage(
            protocol_version=PROTOCOL_VERSION,
            type="status",
            message_id=message_id,
            sequence_id=sequence_id,
            emitted_ts_ms=emitted_ts_ms,
            payload=StatusPayload(
                state=state,
                capture_available=capture_available,
                applied_revision=None,
                code=code,
                detail=detail,
            ),
        )

    def command_ok(
        self,
        *,
        command_id: str,
        command_type: Literal["shutdown"],
    ) -> CommandResultMessage:
        message_id, sequence_id, emitted_ts_ms = self._metadata()
        return CommandResultMessage(
            protocol_version=PROTOCOL_VERSION,
            type="command_result",
            message_id=message_id,
            sequence_id=sequence_id,
            emitted_ts_ms=emitted_ts_ms,
            payload=CommandResultPayload(
                command_id=command_id,
                command_type=command_type,
                status="ok",
                applied_revision=None,
                capture=None,
                error=None,
            ),
        )

    def command_error(
        self,
        *,
        command_id: str,
        command_type: CommandType,
        code: str,
        message: str,
        retryable: bool,
    ) -> CommandResultMessage:
        message_id, sequence_id, emitted_ts_ms = self._metadata()
        return CommandResultMessage(
            protocol_version=PROTOCOL_VERSION,
            type="command_result",
            message_id=message_id,
            sequence_id=sequence_id,
            emitted_ts_ms=emitted_ts_ms,
            payload=CommandResultPayload(
                command_id=command_id,
                command_type=command_type,
                status="error",
                applied_revision=None,
                capture=None,
                error=ProtocolFailurePayload(
                    code=code,
                    message=message,
                    retryable=retryable,
                ),
            ),
        )

    def _metadata(self) -> tuple[str, int, int]:
        with self._lock:
            self._sequence_id += 1
            return self._message_id_factory(), self._sequence_id, self._clock_ms()


def _finder_payload(signal: MiningFinderSignal, *, roi_name: str) -> FinderObservationPayload:
    debug = {key: float(value) for key, value in signal.debug.items()}
    match signal.kind:
        case "probe_fired":
            return ProbeFiredPayload(
                kind="probe_fired",
                roi_name=roi_name,
                debug=debug,
                modes_mask=signal.modes_mask,
                probes_per_drop=signal.probes_per_drop,
                ammo_per_drop=signal.ammo_per_drop,
                raw_status_text=signal.raw_text,
            )
        case "finder_modes_changed":
            if signal.modes_mask is None:
                raise ValueError("finder_modes_changed requires modes_mask")
            return FinderModesChangedPayload(
                kind="finder_modes_changed",
                roi_name=roi_name,
                debug=debug,
                modes_mask=signal.modes_mask,
                previous_modes_mask=signal.previous_modes_mask,
            )
        case "finder_mode_invalidated":
            return FinderModeInvalidatedPayload(
                kind="finder_mode_invalidated",
                roi_name=roi_name,
                debug=debug,
                previous_modes_mask=signal.previous_modes_mask,
            )
        case "finder_units_changed":
            return FinderUnitsChangedPayload(
                kind="finder_units_changed",
                roi_name=roi_name,
                debug=debug,
                probes_per_drop=signal.probes_per_drop,
                ammo_per_drop=signal.ammo_per_drop,
                raw_units_text=signal.raw_text,
            )
        case "finder_hit_hint":
            if (
                signal.hit_size_label is None
                or signal.hit_size_index is None
                or signal.resource_name is None
            ):
                raise ValueError("finder_hit_hint requires size label, index, and resource")
            return FinderHitHintPayload(
                kind="finder_hit_hint",
                roi_name=roi_name,
                debug=debug,
                size_label=signal.hit_size_label,
                size_index=signal.hit_size_index,
                resource_name=signal.resource_name,
                range_m=signal.range_m,
                depth_m=signal.depth_m,
                raw_status_text=signal.raw_text,
                raw_details_text=signal.raw_details_text,
            )
        case "finder_no_resources":
            return FinderNoResourcesPayload(
                kind="finder_no_resources",
                roi_name=roi_name,
                debug=debug,
                raw_status_text=signal.raw_text,
            )

    raise ValueError(f"Unsupported finder signal kind: {signal.kind}")


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


def _new_message_id() -> str:
    return uuid.uuid4().hex
