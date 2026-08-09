from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Any

from zml_ocr_agent.runner import start_ocr_input
from zml_ocr_agent.tesserocr_runtime import preload_tesserocr_preserving_sigint_handler
from zml_ocr_protocol import (
    AgentToBridgeMessage,
    FinderSignalMessage,
    PositionMessage,
    StatusMessage,
)

from zml_game_bridge.application.mining.signals.finder import (
    FinderHitHintSignal,
    FinderModeInvalidatedSignal,
    FinderModesChangedSignal,
    FinderNoResourcesSignal,
    FinderUnitsChangedSignal,
    ProbeFiredSignal,
)
from zml_game_bridge.application.position.model import PositionSnapshot
from zml_game_bridge.domain.position import WorldPos
from zml_game_bridge.events.base import SignalBase
from zml_game_bridge.events.contracts import SignalSink
from zml_game_bridge.runtime.supervisor import WorkerSupervisor

_OCR_WORKER_NAME = "ocr_worker"

PositionSnapshotSink = Callable[[PositionSnapshot], None]
OcrRunner = Callable[..., None]
OcrPreloader = Callable[[], Any]
ClockMs = Callable[[], int]


@dataclass(frozen=True, slots=True)
class EmbeddedOcrInputConfig:
    enabled: bool
    roi_profile_path: Path
    finder_recording_modes: str
    finder_recording_dir: Path
    finder_recording_interval_s: float
    finder_recording_max_samples: int
    finder_presence_check_enabled: bool
    position_roi_snapshot_enabled: bool
    position_roi_snapshot_dir: Path
    position_roi_snapshot_interval_s: float
    position_roi_snapshot_max_samples: int
    ocr_profiling_enabled: bool
    ocr_profiling_interval_s: float


class EmbeddedOcrInputSource:
    """Run the current in-process OCR implementation behind the runtime port."""

    def __init__(
        self,
        *,
        config: EmbeddedOcrInputConfig,
        supervisor: WorkerSupervisor,
        position_sink: PositionSnapshotSink,
        signal_sink: SignalSink,
        runner: OcrRunner = start_ocr_input,
        preloader: OcrPreloader = preload_tesserocr_preserving_sigint_handler,
        clock_ms: ClockMs | None = None,
    ) -> None:
        self._config = config
        self._supervisor = supervisor
        self._position_sink = position_sink
        self._signal_sink = signal_sink
        self._runner = runner
        self._preloader = preloader
        self._clock_ms = clock_ms or _now_ms

    def start(self, *, stop_event: Event) -> None:
        if not self._config.enabled:
            return

        try:
            # Keep the preload on the main thread so tesserocr cannot replace
            # Uvicorn's SIGINT handler from the OCR worker thread.
            self._preloader()
        except Exception as exc:
            self._supervisor.mark_crashed(_OCR_WORKER_NAME, exc)
            raise

        self._supervisor.start_thread(
            name=_OCR_WORKER_NAME,
            target=self._runner,
            worker_kwargs={
                "message_sink": self._on_message,
                "stop_event": stop_event,
                "roi_profile_path": self._config.roi_profile_path,
                "finder_recording_modes": self._config.finder_recording_modes,
                "finder_recording_dir": self._config.finder_recording_dir,
                "finder_recording_interval_s": self._config.finder_recording_interval_s,
                "finder_recording_max_samples": self._config.finder_recording_max_samples,
                "finder_presence_check_enabled": self._config.finder_presence_check_enabled,
                "position_roi_snapshot_enabled": self._config.position_roi_snapshot_enabled,
                "position_roi_snapshot_dir": self._config.position_roi_snapshot_dir,
                "position_roi_snapshot_interval_s": (self._config.position_roi_snapshot_interval_s),
                "position_roi_snapshot_max_samples": (
                    self._config.position_roi_snapshot_max_samples
                ),
                "ocr_profiling_enabled": self._config.ocr_profiling_enabled,
                "ocr_profiling_interval_s": self._config.ocr_profiling_interval_s,
            },
        )

    def stop(self) -> None:
        if self._config.enabled:
            self._supervisor.join_thread(_OCR_WORKER_NAME)

    def _on_message(self, message: AgentToBridgeMessage) -> None:
        if isinstance(message, PositionMessage):
            self._on_position(message)
            return
        if isinstance(message, FinderSignalMessage):
            self._signal_sink(_to_finder_signal(message))
            return
        if isinstance(message, StatusMessage):
            self._on_status(message)

    def _on_position(self, message: PositionMessage) -> None:
        position = message.payload.position
        self._position_sink(
            PositionSnapshot(
                observed_ts_ms=message.observed_ts_ms,
                received_ts_ms=self._clock_ms(),
                position=WorldPos(
                    planet_name=position.planet_name,
                    x=position.x,
                    y=position.y,
                    z=position.z,
                ),
                source="ocr",
            )
        )

    def _on_status(self, message: StatusMessage) -> None:
        if message.payload.state == "running":
            self._supervisor.mark_running(_OCR_WORKER_NAME)
            return
        self._supervisor.mark_degraded(
            _OCR_WORKER_NAME,
            message.payload.detail or "Entropia Universe window is unavailable",
        )


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


def _to_finder_signal(message: FinderSignalMessage) -> SignalBase:
    payload = message.payload
    match payload.kind:
        case "probe_fired":
            return ProbeFiredSignal(
                ts_ms=message.observed_ts_ms,
                # The runtime coordinator snapshots current position through PositionProvider.
                position=None,
                modes_mask=payload.modes_mask,
                probes_per_drop=payload.probes_per_drop,
                ammo_per_drop=payload.ammo_per_drop,
                raw_status_text=payload.raw_status_text,
                roi_name=payload.roi_name,
                debug=payload.debug,
            )
        case "finder_modes_changed":
            return FinderModesChangedSignal(
                ts_ms=message.observed_ts_ms,
                modes_mask=payload.modes_mask,
                previous_modes_mask=payload.previous_modes_mask,
                roi_name=payload.roi_name,
                debug=payload.debug,
            )
        case "finder_mode_invalidated":
            return FinderModeInvalidatedSignal(
                ts_ms=message.observed_ts_ms,
                previous_modes_mask=payload.previous_modes_mask,
                roi_name=payload.roi_name,
                debug=payload.debug,
            )
        case "finder_units_changed":
            return FinderUnitsChangedSignal(
                ts_ms=message.observed_ts_ms,
                probes_per_drop=payload.probes_per_drop,
                ammo_per_drop=payload.ammo_per_drop,
                raw_text=payload.raw_units_text,
                roi_name=payload.roi_name,
            )
        case "finder_hit_hint":
            return FinderHitHintSignal(
                ts_ms=message.observed_ts_ms,
                size_label=payload.size_label,
                size_index=payload.size_index,
                resource_name=payload.resource_name,
                range_m=payload.range_m,
                depth_m=payload.depth_m,
                raw_status_text=payload.raw_status_text,
                raw_details_text=payload.raw_details_text,
                roi_name=payload.roi_name,
            )
        case "finder_no_resources":
            return FinderNoResourcesSignal(
                ts_ms=message.observed_ts_ms,
                raw_status_text=payload.raw_status_text,
                roi_name=payload.roi_name,
            )
