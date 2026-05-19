from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterator

from zml_game_bridge.domain.mining import MiningMode
from zml_game_bridge.domain.position import WorldPos
from zml_game_bridge.events.contracts import SignalSink
from zml_game_bridge.inputs.ocr.pipelines.mining_finder.signals import (
    FinderHitHintSignal,
    FinderModesChangedSignal,
    FinderNoResourcesSignal,
    FinderUnitsChangedSignal,
    ProbeFiredSignal,
)

MOCK_ROI_NAME = "mock_mining_input"
DEFAULT_INTERVAL_MS = 3_000
MIN_INTERVAL_MS = 500

_MOCK_PATH: tuple[WorldPos, ...] = (
    WorldPos(planet_name="Calypso", x=58_890, y=84_639, z=None),
    WorldPos(planet_name="Calypso", x=58_899, y=84_647, z=None),
    WorldPos(planet_name="Calypso", x=58_913, y=84_653, z=None),
    WorldPos(planet_name="Calypso", x=58_926, y=84_660, z=None),
    WorldPos(planet_name="Calypso", x=58_940, y=84_667, z=None),
    WorldPos(planet_name="Calypso", x=58_952, y=84_676, z=None),
)

_MOCK_HITS: tuple[tuple[str, str, int, float, float], ...] = (
    ("Lysterium Stone", "Minimal", 1, 51.14, 53.0),
    ("Belkar Stone", "Tiny", 2, 38.7, 119.0),
    ("Crude Oil", "Very Poor", 3, 24.2, 82.0),
)

logger = logging.getLogger(__name__)


def iter_mock_mining_signals(
    *,
    start_ts_ms: int,
    drop_count: int,
) -> Iterator[
    FinderModesChangedSignal
    | FinderUnitsChangedSignal
    | ProbeFiredSignal
    | FinderHitHintSignal
    | FinderNoResourcesSignal
]:
    yield FinderModesChangedSignal(
        ts_ms=start_ts_ms,
        modes_mask=int(MiningMode.ORE),
        previous_modes_mask=None,
        roi_name=MOCK_ROI_NAME,
    )
    yield FinderUnitsChangedSignal(
        ts_ms=start_ts_ms + 100,
        probes_per_drop=None,
        ammo_per_drop=1_000,
        raw_text="UNIVERSAL AMMO\n1000",
        roi_name=MOCK_ROI_NAME,
    )

    for drop_index in range(drop_count):
        drop_ts_ms = start_ts_ms + 1_000 + drop_index * 6_000
        yield _mock_probe_signal(drop_index=drop_index, ts_ms=drop_ts_ms)
        yield _mock_result_signal(drop_index=drop_index, ts_ms=drop_ts_ms + 3_500)


def start_mock_mining_input(
    *,
    signal_sink: SignalSink,
    stop_event: threading.Event,
    interval_ms: int = DEFAULT_INTERVAL_MS,
) -> None:
    interval_s = max(MIN_INTERVAL_MS, interval_ms) / 1_000
    start_ts_ms = _now_ms()

    for signal in iter_mock_mining_signals(start_ts_ms=start_ts_ms, drop_count=0):
        if stop_event.is_set():
            return
        _log_mock_signal(signal)
        signal_sink(signal)

    drop_index = 0
    while not stop_event.is_set():
        drop_ts_ms = _now_ms()
        signal = _mock_probe_signal(drop_index=drop_index, ts_ms=drop_ts_ms)
        _log_mock_signal(signal)
        signal_sink(signal)

        if stop_event.wait(min(1.5, interval_s / 2)):
            return

        signal = _mock_result_signal(drop_index=drop_index, ts_ms=_now_ms())
        _log_mock_signal(signal)
        signal_sink(signal)
        drop_index += 1

        stop_event.wait(interval_s)


def _mock_probe_signal(*, drop_index: int, ts_ms: int) -> ProbeFiredSignal:
    return ProbeFiredSignal(
        ts_ms=ts_ms,
        position=_MOCK_PATH[drop_index % len(_MOCK_PATH)],
        modes_mask=int(MiningMode.ORE),
        probes_per_drop=None,
        ammo_per_drop=1_000,
        raw_status_text="Sending probe...",
        roi_name=MOCK_ROI_NAME,
    )


def _mock_result_signal(
    *,
    drop_index: int,
    ts_ms: int,
) -> FinderHitHintSignal | FinderNoResourcesSignal:
    if drop_index % 3 != 2:
        return FinderNoResourcesSignal(
            ts_ms=ts_ms,
            raw_status_text="No resources found. Try again\nsomewhere else-",
            roi_name=MOCK_ROI_NAME,
        )

    resource_name, size_label, size_index, range_m, depth_m = _MOCK_HITS[
        (drop_index // 3) % len(_MOCK_HITS)
    ]
    return FinderHitHintSignal(
        ts_ms=ts_ms,
        size_label=size_label,
        size_index=size_index,
        resource_name=resource_name,
        range_m=range_m,
        depth_m=depth_m,
        raw_status_text=(
            "You have found a resource. Follow the arrows to its location.\n"
            f"Estimated size: {size_label} ({size_index})"
        ),
        raw_details_text=f"RANGE {range_m}m\nDEPTH {depth_m:g}m\nTYPE {resource_name}",
        roi_name=MOCK_ROI_NAME,
    )


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


def _log_mock_signal(
    signal: FinderModesChangedSignal
    | FinderUnitsChangedSignal
    | ProbeFiredSignal
    | FinderHitHintSignal
    | FinderNoResourcesSignal,
) -> None:
    logger.info(
        "mock mining signal type=%s ts=%s position=%s modes=%s ammo=%s resource=%s",
        type(signal).__name__,
        signal.ts_ms,
        getattr(signal, "position", None),
        getattr(signal, "modes_mask", None),
        getattr(signal, "ammo_per_drop", None),
        getattr(signal, "resource_name", None),
    )
