from __future__ import annotations

import time
from collections.abc import Callable

from zml_ocr_protocol import FinderSignalMessage, PositionMessage

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

PositionSnapshotSink = Callable[[PositionSnapshot], None]
ClockMs = Callable[[], int]


class OcrAgentMessageMapper:
    def __init__(
        self,
        *,
        position_sink: PositionSnapshotSink,
        signal_sink: SignalSink,
        clock_ms: ClockMs | None = None,
    ) -> None:
        self._position_sink = position_sink
        self._signal_sink = signal_sink
        self._clock_ms = clock_ms or _now_ms

    def map_position(self, message: PositionMessage) -> None:
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

    def map_finder(self, message: FinderSignalMessage) -> None:
        self._signal_sink(_to_finder_signal(message))


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


def _now_ms() -> int:
    return time.time_ns() // 1_000_000
