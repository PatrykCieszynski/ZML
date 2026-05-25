from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from zml_game_bridge.domain.mining_events import (
    MiningClaimDeedReceivedEvent,
    MiningEnhancerBrokeEvent,
    MiningItemReceivedEvent,
)
from zml_game_bridge.domain.money import Mpec
from zml_game_bridge.events.base import EventBase, SignalBase
from zml_game_bridge.inputs.chat.signals import (
    ChatSignalBase,
    EnhancerBrokeSignal,
    ItemReceivedSignal,
    ResourceClaimedSignal,
    ResourceDepletedSignal,
)
from zml_game_bridge.resources.mining_resources import MiningResourceCatalog

logger = logging.getLogger(__name__)
ExtractionCostProvider = Callable[[], Mpec | None]
DEFAULT_PENDING_DEED_LINK_WINDOW_MS = 10_000


@dataclass(frozen=True, slots=True)
class PendingClaimDeed:
    event_dt: datetime
    mining_type: str
    item_name: str
    qty: int
    value_mpec: Mpec
    raw: str


class MiningChatCorrelator:
    def __init__(
        self,
        *,
        resource_catalog: MiningResourceCatalog | None = None,
        extraction_cost_provider: ExtractionCostProvider | None = None,
        pending_deed_link_window_ms: int = DEFAULT_PENDING_DEED_LINK_WINDOW_MS,
    ) -> None:
        self._pending_deeds: list[PendingClaimDeed] = []
        self._resource_catalog = resource_catalog or MiningResourceCatalog()
        self._extraction_cost_provider = extraction_cost_provider or _missing_extraction_cost
        self._pending_deed_link_window = timedelta(milliseconds=pending_deed_link_window_ms)

    def process_signal(self, signal: SignalBase) -> list[EventBase]:
        if not isinstance(signal, ChatSignalBase):
            return []
        self._drop_stale_pending_deeds(now=signal.event_dt)

        if isinstance(signal, ItemReceivedSignal):
            claim_deed = _to_pending_claim_deed(signal)
            if claim_deed is not None:
                self._pending_deeds.append(claim_deed)
                return []
            event = self._record_item_received(signal)
            return [event] if event is not None else []

        if isinstance(signal, ResourceClaimedSignal):
            event = self._record_claim_deed_received(signal)
            return [event] if event is not None else []

        if isinstance(signal, ResourceDepletedSignal):
            # A depleted claim event must name the concrete claim_id for UI patching.
            # Claim lifecycle correlation will handle this once active claims are tracked.
            return []

        if isinstance(signal, EnhancerBrokeSignal):
            return [self._record_enhancer_broke(signal)]

        return []

    def _record_claim_deed_received(
        self,
        signal: ResourceClaimedSignal,
    ) -> MiningClaimDeedReceivedEvent | None:
        deed = self._pending_deeds.pop(0) if self._pending_deeds else None
        if deed is None:
            logger.warning(
                "resource_claimed_without_pending_deed resource=%r event_dt=%s",
                signal.resource_name,
                signal.event_dt,
            )
            return None

        raw = f"{deed.raw}\n{signal.raw}"
        event = MiningClaimDeedReceivedEvent(
            event_dt=signal.event_dt,
            resource_name=signal.resource_name,
            mining_type=deed.mining_type,
            deed_item_name=deed.item_name,
            qty=deed.qty,
            value_mpec=deed.value_mpec,
            raw=raw,
            received_raw=deed.raw,
            claimed_raw=signal.raw,
        )
        learned = self._resource_catalog.learn_resource(
            name=signal.resource_name,
            resource_type=deed.mining_type,
            event_dt=signal.event_dt,
        )
        logger.debug(
            "claim_deed_received_recorded event_type=%s resource=%r mining_type=%s "
            "learned_source=%s event_dt=%s",
            type(event).__name__,
            event.resource_name,
            event.mining_type,
            learned.source,
            event.event_dt,
        )
        return event

    def _drop_stale_pending_deeds(self, *, now: datetime) -> None:
        cutoff = now - self._pending_deed_link_window
        while self._pending_deeds and self._pending_deeds[0].event_dt < cutoff:
            stale = self._pending_deeds.pop(0)
            logger.warning(
                "pending_claim_deed_expired item=%r mining_type=%s deed_dt=%s now=%s",
                stale.item_name,
                stale.mining_type,
                stale.event_dt,
                now,
            )

    def _record_item_received(self, signal: ItemReceivedSignal) -> MiningItemReceivedEvent | None:
        resource = self._resource_catalog.get(signal.item_name)
        if resource is None or not resource.track_as_loot:
            logger.debug(
                "item_received_ignored item=%r qty=%s value_mpec=%s reason=not_tracked_resource",
                signal.item_name,
                signal.qty,
                signal.value_mpec,
            )
            return None

        event = MiningItemReceivedEvent(
            event_dt=signal.event_dt,
            item_name=signal.item_name,
            qty=signal.qty,
            value_mpec=signal.value_mpec,
            raw=signal.raw,
            extraction_cost_mpec=self._extraction_cost_provider(),
        )
        logger.debug(
            "item_received_recorded event_type=%s item=%r qty=%s value_mpec=%s "
            "extraction_cost_mpec=%s event_dt=%s",
            type(event).__name__,
            event.item_name,
            event.qty,
            event.value_mpec,
            event.extraction_cost_mpec,
            event.event_dt,
        )
        return event

    def _record_enhancer_broke(
        self,
        signal: EnhancerBrokeSignal,
    ) -> MiningEnhancerBrokeEvent:
        event = MiningEnhancerBrokeEvent(
            event_dt=signal.event_dt,
            enhancer_name=signal.enhancer_name,
            item_name=signal.item_name,
            remaining=signal.remaining,
            raw=signal.raw,
        )
        logger.debug(
            "enhancer_broke_recorded event_type=%s enhancer=%r item=%r remaining=%s event_dt=%s",
            type(event).__name__,
            event.enhancer_name,
            event.item_name,
            event.remaining,
            event.event_dt,
        )
        return event


def _to_pending_claim_deed(signal: ItemReceivedSignal) -> PendingClaimDeed | None:
    mining_type = _mining_type_from_deed_item_name(signal.item_name)
    if mining_type is None:
        return None
    return PendingClaimDeed(
        event_dt=signal.event_dt,
        mining_type=mining_type,
        item_name=signal.item_name,
        qty=signal.qty,
        value_mpec=signal.value_mpec,
        raw=signal.raw,
    )


def _mining_type_from_deed_item_name(item_name: str) -> str | None:
    normalized = " ".join(item_name.strip().lower().split())
    match normalized:
        case "mineral resource deed":
            return "ore"
        case "energy matter resource deed":
            return "enmatter"
        case "treasure resource deed":
            return "treasure"
        case _:
            return None


def _missing_extraction_cost() -> Mpec | None:
    return None
