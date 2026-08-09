from __future__ import annotations

from typing import Annotated, Final, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

PROTOCOL_VERSION: Final = 1
SUPPORTED_PROTOCOL_VERSIONS: Final = (PROTOCOL_VERSION,)

type MessageId = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9a-f]{32}$"),
]
type TimestampMs = Annotated[int, Field(ge=0)]
type SequenceId = Annotated[int, Field(ge=0)]
type ConfigRevision = Annotated[int, Field(ge=1)]
type ModesMask = Annotated[int, Field(ge=0, le=7)]
type NonNegativeInt = Annotated[int, Field(ge=0)]
type PositiveInt = Annotated[int, Field(gt=0)]
type Confidence = Annotated[float, Field(ge=0.0, le=1.0)]
type NonNegativeFloat = Annotated[float, Field(ge=0.0)]
type NonEmptyText = Annotated[str, StringConstraints(min_length=1, max_length=512)]
type CapabilityName = Annotated[
    str,
    StringConstraints(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$"),
]
type WirePath = Annotated[str, StringConstraints(min_length=1, max_length=4096)]
type PathToken = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$",
    ),
]


class WireModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        allow_inf_nan=False,
    )


class WorldPositionPayload(WireModel):
    planet_name: str | None
    x: int
    y: int
    z: int | None


class PositionObservationPayload(WireModel):
    position: WorldPositionPayload
    confidence: Confidence | None
    roi_name: NonEmptyText


class FinderPayloadBase(WireModel):
    roi_name: NonEmptyText
    debug: dict[str, float]


class ProbeFiredPayload(FinderPayloadBase):
    kind: Literal["probe_fired"]
    modes_mask: ModesMask | None
    probes_per_drop: NonNegativeInt | None
    ammo_per_drop: NonNegativeInt | None
    raw_status_text: str | None


class FinderModesChangedPayload(FinderPayloadBase):
    kind: Literal["finder_modes_changed"]
    modes_mask: ModesMask
    previous_modes_mask: ModesMask | None


class FinderModeInvalidatedPayload(FinderPayloadBase):
    kind: Literal["finder_mode_invalidated"]
    previous_modes_mask: ModesMask | None


class FinderUnitsChangedPayload(FinderPayloadBase):
    kind: Literal["finder_units_changed"]
    probes_per_drop: NonNegativeInt | None
    ammo_per_drop: NonNegativeInt | None
    raw_units_text: str | None

    @model_validator(mode="after")
    def require_at_least_one_unit(self) -> FinderUnitsChangedPayload:
        if self.probes_per_drop is None and self.ammo_per_drop is None:
            raise ValueError("finder_units_changed requires at least one unit value")
        return self


class FinderHitHintPayload(FinderPayloadBase):
    kind: Literal["finder_hit_hint"]
    size_label: NonEmptyText
    size_index: PositiveInt
    resource_name: NonEmptyText
    range_m: NonNegativeFloat | None
    depth_m: NonNegativeFloat | None
    raw_status_text: str | None
    raw_details_text: str | None


class FinderNoResourcesPayload(FinderPayloadBase):
    kind: Literal["finder_no_resources"]
    raw_status_text: str | None


type FinderObservationPayload = Annotated[
    ProbeFiredPayload
    | FinderModesChangedPayload
    | FinderModeInvalidatedPayload
    | FinderUnitsChangedPayload
    | FinderHitHintPayload
    | FinderNoResourcesPayload,
    Field(discriminator="kind"),
]


AgentStatusState = Literal["running", "waiting_for_window", "degraded"]


class StatusPayload(WireModel):
    state: AgentStatusState
    capture_available: bool
    applied_revision: ConfigRevision | None
    code: str | None
    detail: str | None

    @model_validator(mode="after")
    def validate_capture_state(self) -> StatusPayload:
        if self.state == "running" and not self.capture_available:
            raise ValueError("running status requires capture_available=true")
        if self.state == "waiting_for_window" and self.capture_available:
            raise ValueError("waiting_for_window status requires capture_available=false")
        return self


class HeartbeatPayload(WireModel):
    state: AgentStatusState
    capture_available: bool
    applied_revision: ConfigRevision | None

    @model_validator(mode="after")
    def validate_capture_state(self) -> HeartbeatPayload:
        if self.state == "running" and not self.capture_available:
            raise ValueError("running heartbeat requires capture_available=true")
        if self.state == "waiting_for_window" and self.capture_available:
            raise ValueError("waiting_for_window heartbeat requires capture_available=false")
        return self


class PixelRectPayload(WireModel):
    x1: NonNegativeInt
    x2: NonNegativeInt
    y1: NonNegativeInt
    y2: NonNegativeInt

    @model_validator(mode="after")
    def validate_order(self) -> PixelRectPayload:
        if self.x2 <= self.x1:
            raise ValueError("x2 must be greater than x1")
        if self.y2 <= self.y1:
            raise ValueError("y2 must be greater than y1")
        return self


class RelativeRectPayload(WireModel):
    x1: Annotated[float, Field(ge=0.0, le=1.0)]
    y1: Annotated[float, Field(ge=0.0, le=1.0)]
    x2: Annotated[float, Field(ge=0.0, le=1.0)]
    y2: Annotated[float, Field(ge=0.0, le=1.0)]

    @model_validator(mode="after")
    def validate_order(self) -> RelativeRectPayload:
        if self.x2 <= self.x1:
            raise ValueError("x2 must be greater than x1")
        if self.y2 <= self.y1:
            raise ValueError("y2 must be greater than y1")
        return self


ScreenRoiAnchor = Literal["top_left", "bottom_left"]


class ScreenRoiPayload(WireModel):
    name: NonEmptyText
    anchor: ScreenRoiAnchor
    x: NonNegativeInt
    y: NonNegativeInt
    width: PositiveInt
    height: PositiveInt
    enabled: bool


class ScreenRoisPayload(WireModel):
    compass: ScreenRoiPayload
    finder: ScreenRoiPayload
    deeds: ScreenRoiPayload
    loot: ScreenRoiPayload | None


class PositionRoisPayload(WireModel):
    planet: PixelRectPayload
    lon: PixelRectPayload
    lat: PixelRectPayload


class FinderPanelPayload(WireModel):
    radar: RelativeRectPayload
    modes: RelativeRectPayload
    details: RelativeRectPayload
    units: RelativeRectPayload
    status: RelativeRectPayload


class OcrRoiProfilePayload(WireModel):
    schema_version: Literal[1]
    name: NonEmptyText
    screen_rois: ScreenRoisPayload
    position_rois: PositionRoisPayload
    finder_panel: FinderPanelPayload


FinderRecordingMode = Literal["manual", "interval"]


class FinderRecordingConfigPayload(WireModel):
    modes: list[FinderRecordingMode]
    directory: WirePath
    interval_ms: PositiveInt
    max_samples: NonNegativeInt

    @field_validator("modes")
    @classmethod
    def require_unique_modes(
        cls,
        modes: list[FinderRecordingMode],
    ) -> list[FinderRecordingMode]:
        if len(modes) != len(set(modes)):
            raise ValueError("finder recording modes must be unique")
        return modes


class FinderRuntimeConfig(WireModel):
    presence_check_enabled: bool
    debug_logging: bool
    recording: FinderRecordingConfigPayload


class PositionSnapshotRecordingConfigPayload(WireModel):
    enabled: bool
    directory: WirePath
    interval_ms: PositiveInt
    max_samples: NonNegativeInt


class PositionRuntimeConfig(WireModel):
    snapshot_recording: PositionSnapshotRecordingConfigPayload


class ProfilingConfig(WireModel):
    enabled: bool
    interval_ms: PositiveInt


class OcrConfigSnapshot(WireModel):
    capture_hz: Annotated[float, Field(gt=0.0, le=60.0)]
    capture_artifacts_dir: WirePath
    roi_profile: OcrRoiProfilePayload
    finder: FinderRuntimeConfig
    position: PositionRuntimeConfig
    profiling: ProfilingConfig


CaptureRegion = Literal["window", "compass", "finder"]


class CaptureArtifactPayload(WireModel):
    capture_id: MessageId
    path_token: PathToken
    format: Literal["png"]
    region: CaptureRegion
    captured_ts_ms: TimestampMs
    width_px: PositiveInt
    height_px: PositiveInt
    roi_name: str | None

    @field_validator("path_token")
    @classmethod
    def reject_parent_path_token(cls, path_token: str) -> str:
        if ".." in path_token:
            raise ValueError("path_token cannot contain '..'")
        return path_token


CommandType = Literal["apply_config", "capture_frame", "shutdown"]
CommandResultStatus = Literal["ok", "error"]


class ProtocolFailurePayload(WireModel):
    code: NonEmptyText
    message: NonEmptyText
    retryable: bool


class CommandResultPayload(WireModel):
    command_id: MessageId
    command_type: CommandType
    status: CommandResultStatus
    applied_revision: ConfigRevision | None
    capture: CaptureArtifactPayload | None
    error: ProtocolFailurePayload | None

    @model_validator(mode="after")
    def validate_result_shape(self) -> CommandResultPayload:
        if self.status == "ok" and self.error is not None:
            raise ValueError("successful command_result requires error=null")
        if self.status == "error" and self.error is None:
            raise ValueError("failed command_result requires error details")
        if self.status == "error" and self.capture is not None:
            raise ValueError("failed command_result requires capture=null")
        if self.command_type == "capture_frame":
            if self.status == "ok" and self.capture is None:
                raise ValueError("successful capture_frame requires capture metadata")
        elif self.capture is not None:
            raise ValueError("only capture_frame may return capture metadata")
        if (
            self.command_type == "apply_config"
            and self.status == "ok"
            and self.applied_revision is None
        ):
            raise ValueError("successful apply_config requires applied_revision")
        return self


class AgentMessageBase(WireModel):
    protocol_version: Literal[1]
    message_id: MessageId
    sequence_id: SequenceId
    emitted_ts_ms: TimestampMs


class HelloPayload(WireModel):
    agent_version: NonEmptyText
    pid: PositiveInt
    started_ts_ms: TimestampMs
    capabilities: list[CapabilityName]

    @field_validator("capabilities")
    @classmethod
    def require_unique_capabilities(cls, capabilities: list[str]) -> list[str]:
        if len(capabilities) != len(set(capabilities)):
            raise ValueError("capabilities must be unique")
        return capabilities


class HelloMessage(AgentMessageBase):
    type: Literal["hello"]
    payload: HelloPayload


class PositionMessage(AgentMessageBase):
    type: Literal["position"]
    observed_ts_ms: TimestampMs
    payload: PositionObservationPayload


class FinderSignalMessage(AgentMessageBase):
    type: Literal["finder_signal"]
    observed_ts_ms: TimestampMs
    payload: FinderObservationPayload


class StatusMessage(AgentMessageBase):
    type: Literal["status"]
    payload: StatusPayload


class HeartbeatMessage(AgentMessageBase):
    type: Literal["heartbeat"]
    payload: HeartbeatPayload


class CommandResultMessage(AgentMessageBase):
    type: Literal["command_result"]
    payload: CommandResultPayload


type AgentToBridgeMessage = Annotated[
    HelloMessage
    | PositionMessage
    | FinderSignalMessage
    | StatusMessage
    | HeartbeatMessage
    | CommandResultMessage,
    Field(discriminator="type"),
]


class BridgeCommandBase(WireModel):
    protocol_version: Literal[1]
    command_id: MessageId
    sent_ts_ms: TimestampMs


class ApplyConfigPayload(WireModel):
    revision: ConfigRevision
    config: OcrConfigSnapshot


class ApplyConfigCommand(BridgeCommandBase):
    type: Literal["apply_config"]
    payload: ApplyConfigPayload


class CaptureFramePayload(WireModel):
    purpose: Literal["calibration", "debug"]
    region: CaptureRegion


class CaptureFrameCommand(BridgeCommandBase):
    type: Literal["capture_frame"]
    payload: CaptureFramePayload


class ShutdownPayload(WireModel):
    reason: Literal["backend_shutdown", "agent_restart", "config_restart"]


class ShutdownCommand(BridgeCommandBase):
    type: Literal["shutdown"]
    payload: ShutdownPayload


type BridgeToAgentMessage = Annotated[
    ApplyConfigCommand | CaptureFrameCommand | ShutdownCommand,
    Field(discriminator="type"),
]

type WireMessage = AgentToBridgeMessage | BridgeToAgentMessage
