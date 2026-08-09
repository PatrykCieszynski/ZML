from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from threading import Event, Thread
from typing import Any, cast

import pytest

from zml_game_bridge.application.mining.signals.finder import ProbeFiredSignal
from zml_game_bridge.application.position.model import PositionSnapshot
from zml_game_bridge.domain.position import WorldPos
from zml_game_bridge.events.base import SignalBase
from zml_game_bridge.inputs.ocr.pipelines.position.model import OcrPosition
from zml_game_bridge.inputs.ocr.source import EmbeddedOcrInputConfig, EmbeddedOcrInputSource
from zml_game_bridge.runtime.supervisor import WorkerSupervisor


class _Supervisor:
    def __init__(self) -> None:
        self.start_calls: list[tuple[str, Callable[..., None], dict[str, Any]]] = []
        self.join_calls: list[str] = []
        self.crashed: list[tuple[str, BaseException]] = []
        self.running: list[str] = []
        self.degraded: list[tuple[str, str]] = []

    def start_thread(
        self,
        *,
        name: str,
        target: Callable[..., None],
        worker_kwargs: dict[str, Any],
    ) -> Thread:
        self.start_calls.append((name, target, worker_kwargs))
        return cast(Thread, object())

    def join_thread(self, name: str, *, timeout_s: float = 5.0) -> bool:
        del timeout_s
        self.join_calls.append(name)
        return True

    def mark_crashed(self, name: str, exc: BaseException) -> None:
        self.crashed.append((name, exc))

    def mark_running(self, name: str) -> None:
        self.running.append(name)

    def mark_degraded(self, name: str, message: str) -> None:
        self.degraded.append((name, message))


def test_embedded_source_wraps_runner_and_maps_outputs() -> None:
    supervisor = _Supervisor()
    positions: list[PositionSnapshot] = []
    signals: list[SignalBase] = []
    preload_calls = 0

    def preload() -> object:
        nonlocal preload_calls
        preload_calls += 1
        return object()

    def runner(**_kwargs: object) -> None:
        pass

    source = EmbeddedOcrInputSource(
        config=_config(),
        supervisor=cast(WorkerSupervisor, supervisor),
        position_sink=positions.append,
        signal_sink=signals.append,
        runner=runner,
        preloader=preload,
        clock_ms=lambda: 2_000,
    )
    stop_event = Event()

    source.start(stop_event=stop_event)

    assert preload_calls == 1
    assert len(supervisor.start_calls) == 1
    worker_name, worker_target, worker_kwargs = supervisor.start_calls[0]
    assert worker_name == "ocr_worker"
    assert worker_target is runner
    assert worker_kwargs["stop_event"] is stop_event
    assert worker_kwargs["roi_profile_path"] == Path("ocr-profile.json")

    position_sink = cast(Callable[[OcrPosition], None], worker_kwargs["position_sink"])
    position_sink(
        OcrPosition(
            ts_ms=1_000,
            position=WorldPos(planet_name="Calypso", x=58_000, y=84_000, z=None),
        )
    )
    assert positions == [
        PositionSnapshot(
            observed_ts_ms=1_000,
            received_ts_ms=2_000,
            position=WorldPos(planet_name="Calypso", x=58_000, y=84_000, z=None),
            source="ocr",
        )
    ]

    signal = ProbeFiredSignal(
        ts_ms=1_500,
        position=None,
        modes_mask=1,
        probes_per_drop=1,
        ammo_per_drop=None,
        raw_status_text="Searching",
        roi_name="finder",
    )
    signal_sink = cast(Callable[[SignalBase], None], worker_kwargs["signal_sink"])
    signal_sink(signal)
    assert signals == [signal]

    capture_status_sink = cast(
        Callable[[bool, str | None], None], worker_kwargs["capture_status_sink"]
    )
    capture_status_sink(False, "window missing")
    capture_status_sink(True, None)
    assert supervisor.degraded == [("ocr_worker", "window missing")]
    assert supervisor.running == ["ocr_worker"]

    source.stop()
    assert supervisor.join_calls == ["ocr_worker"]


def test_embedded_source_is_noop_when_disabled() -> None:
    supervisor = _Supervisor()
    source = EmbeddedOcrInputSource(
        config=_config(enabled=False),
        supervisor=cast(WorkerSupervisor, supervisor),
        position_sink=lambda _snapshot: None,
        signal_sink=lambda _signal: None,
        preloader=lambda: pytest.fail("disabled source must not preload tesserocr"),
    )

    source.start(stop_event=Event())
    source.stop()

    assert supervisor.start_calls == []
    assert supervisor.join_calls == []


def test_embedded_source_marks_preload_failure_as_crashed() -> None:
    supervisor = _Supervisor()
    error = RuntimeError("tesserocr unavailable")

    def fail_preload() -> object:
        raise error

    source = EmbeddedOcrInputSource(
        config=_config(),
        supervisor=cast(WorkerSupervisor, supervisor),
        position_sink=lambda _snapshot: None,
        signal_sink=lambda _signal: None,
        preloader=fail_preload,
    )

    with pytest.raises(RuntimeError, match="tesserocr unavailable"):
        source.start(stop_event=Event())

    assert supervisor.crashed == [("ocr_worker", error)]
    assert supervisor.start_calls == []


def _config(*, enabled: bool = True) -> EmbeddedOcrInputConfig:
    return EmbeddedOcrInputConfig(
        enabled=enabled,
        roi_profile_path=Path("ocr-profile.json"),
        finder_recording_modes="off",
        finder_recording_dir=Path("finder-recordings"),
        finder_recording_interval_s=1.5,
        finder_recording_max_samples=50,
        finder_presence_check_enabled=True,
        position_roi_snapshot_enabled=False,
        position_roi_snapshot_dir=Path("position-snapshots"),
        position_roi_snapshot_interval_s=2.5,
        position_roi_snapshot_max_samples=25,
        ocr_profiling_enabled=True,
        ocr_profiling_interval_s=10.0,
    )
