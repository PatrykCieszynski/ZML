from __future__ import annotations

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

from zml_game_bridge.application.position.model import PositionSnapshot
from zml_game_bridge.events.contracts import SignalSink
from zml_game_bridge.runtime.ocr_agent.message_mapper import OcrAgentMessageMapper
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
        self._mapper = OcrAgentMessageMapper(
            position_sink=position_sink,
            signal_sink=signal_sink,
            clock_ms=clock_ms,
        )
        self._runner = runner
        self._preloader = preloader

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
            self._mapper.map_position(message)
            return
        if isinstance(message, FinderSignalMessage):
            self._mapper.map_finder(message)
            return
        if isinstance(message, StatusMessage):
            self._on_status(message)

    def _on_status(self, message: StatusMessage) -> None:
        if message.payload.state == "running":
            self._supervisor.mark_running(_OCR_WORKER_NAME)
            return
        self._supervisor.mark_degraded(
            _OCR_WORKER_NAME,
            message.payload.detail or "Entropia Universe window is unavailable",
        )
