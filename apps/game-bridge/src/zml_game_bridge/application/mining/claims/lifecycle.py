from __future__ import annotations

import logging
import math
from collections.abc import Iterable
from dataclasses import dataclass

from zml_game_bridge.application.mining.claims.commands import (
    IgnoreMiningClaimCommand,
    MarkMiningClaimDepletedCommand,
)
from zml_game_bridge.application.mining.settings import IdFactory, MiningCoordinatorConfig
from zml_game_bridge.application.position.provider import PositionProvider
from zml_game_bridge.domain.mining_events import (
    MiningClaimCreatedEvent,
    MiningClaimDepletedEvent,
    MiningClaimIgnoredEvent,
    MiningDropEvent,
    MiningHitHintEvent,
    MiningNoResourcesEvent,
)
from zml_game_bridge.domain.position import WorldPos
from zml_game_bridge.events.base import EventBase, SignalBase
from zml_game_bridge.inputs.chat.signals import ResourceDepletedSignal
from zml_game_bridge.resources.mining_resources import MiningResourceCatalog

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ActiveClaim:
    claim_id: str
    drop_id: str | None
    hit_id: str | None
    run_id: int | None
    segment_id: str | None
    position: WorldPos | None
    search_radius_m: float | None


class ClaimLifecycleCorrelator:
    def __init__(
        self,
        *,
        config: MiningCoordinatorConfig,
        id_factory: IdFactory,
        position_provider: PositionProvider | None = None,
        resource_catalog: MiningResourceCatalog | None = None,
    ) -> None:
        self._config = config
        self._id_factory = id_factory
        self._position_provider = position_provider or _none_position_provider
        self._resource_catalog = resource_catalog or MiningResourceCatalog()
        self._drops_by_id: dict[str, MiningDropEvent] = {}
        self._active_claims: dict[str, ActiveClaim] = {}

    def restore_active_claims(self, claims: Iterable[ActiveClaim]) -> None:
        self._active_claims = {claim.claim_id: claim for claim in claims}
        logger.info("claim_lifecycle_restored active_claims=%s", len(self._active_claims))

    def process_event(self, event: EventBase) -> list[EventBase]:
        if isinstance(event, MiningDropEvent):
            self._prune_stale_drops(event.observed_ts_ms)
            self._drops_by_id[event.drop_id] = event
            return []

        if isinstance(event, MiningHitHintEvent):
            return [self._create_claim(event)]

        if isinstance(event, MiningNoResourcesEvent):
            if event.drop_id is not None:
                self._drops_by_id.pop(event.drop_id, None)
            return []

        return []

    def process_signal(self, signal: SignalBase) -> list[EventBase]:
        if isinstance(signal, ResourceDepletedSignal):
            event = self._deplete_nearest_claim(signal)
            return [event] if event is not None else []

        return []

    def deplete_claim(self, command: MarkMiningClaimDepletedCommand) -> MiningClaimDepletedEvent:
        claim = self._active_claims.pop(command.claim_id, None)
        event = MiningClaimDepletedEvent(
            claim_id=command.claim_id,
            drop_id=claim.drop_id if claim is not None else command.drop_id,
            hit_id=claim.hit_id if claim is not None else command.hit_id,
            event_dt=command.event_dt,
            position=command.position,
            distance_m=command.distance_m,
            raw=command.raw,
            run_id=claim.run_id if claim is not None else command.run_id,
            segment_id=claim.segment_id if claim is not None else command.segment_id,
        )
        logger.debug(
            "claim_depleted_manual event_type=%s claim_id=%s distance_m=%.2f event_dt=%s",
            type(event).__name__,
            event.claim_id,
            event.distance_m,
            event.event_dt,
        )
        return event

    def ignore_claim(self, command: IgnoreMiningClaimCommand) -> MiningClaimIgnoredEvent:
        claim = self._active_claims.pop(command.claim_id, None)
        event = MiningClaimIgnoredEvent(
            claim_id=command.claim_id,
            ignored_ts_ms=command.ignored_ts_ms,
            reason=command.reason,
            drop_id=claim.drop_id if claim is not None else command.drop_id,
            hit_id=claim.hit_id if claim is not None else command.hit_id,
            run_id=claim.run_id if claim is not None else command.run_id,
            segment_id=claim.segment_id if claim is not None else command.segment_id,
        )
        logger.debug(
            "claim_ignored event_type=%s claim_id=%s reason=%r",
            type(event).__name__,
            event.claim_id,
            event.reason,
        )
        return event

    def _create_claim(self, event: MiningHitHintEvent) -> MiningClaimCreatedEvent:
        drop = self._drops_by_id.get(event.drop_id) if event.drop_id is not None else None
        if event.drop_id is not None:
            # TODO: Multi-mode drops can produce multiple claim deeds for one drop.
            # Keep this cache entry for the full correlation window once deed OCR/chat
            # claim correlation can create more than one claim from the same drop.
            self._drops_by_id.pop(event.drop_id, None)
        claim_id = self._id_factory()
        position = event.position if event.position is not None else drop.position if drop else None
        search_radius_m = drop.drop_radius_m if drop is not None else None
        run_id = drop.run_id if drop is not None else None
        segment_id = drop.segment_id if drop is not None else None

        created = MiningClaimCreatedEvent(
            claim_id=claim_id,
            hit_id=event.hit_id,
            drop_id=event.drop_id,
            observed_ts_ms=event.observed_ts_ms,
            position=position,
            search_radius_m=search_radius_m,
            resource_name=event.resource_name,
            mining_type=self._resolve_mining_type(event.resource_name),
            size_label=event.size_label,
            size_index=event.size_index,
            expected_expires_ts_ms=event.expected_expires_ts_ms,
            range_m=event.range_m,
            depth_m=event.depth_m,
            run_id=run_id,
            segment_id=segment_id,
        )
        self._active_claims[claim_id] = ActiveClaim(
            claim_id=claim_id,
            drop_id=event.drop_id,
            hit_id=event.hit_id,
            run_id=run_id,
            segment_id=segment_id,
            position=position,
            search_radius_m=search_radius_m,
        )
        logger.debug(
            "claim_created event_type=%s claim_id=%s hit_id=%s drop_id=%s resource=%r",
            type(created).__name__,
            created.claim_id,
            created.hit_id,
            created.drop_id,
            created.resource_name,
        )
        return created

    def _prune_stale_drops(self, observed_ts_ms: int) -> None:
        stale_before_ts_ms = observed_ts_ms - self._config.result_link_window_ms
        stale_drop_ids = [
            drop_id
            for drop_id, drop in self._drops_by_id.items()
            if drop.observed_ts_ms < stale_before_ts_ms
        ]
        for drop_id in stale_drop_ids:
            del self._drops_by_id[drop_id]
        if stale_drop_ids:
            logger.debug("claim_lifecycle_pruned_stale_drops count=%s", len(stale_drop_ids))

    def _resolve_mining_type(self, resource_name: str | None) -> str | None:
        if resource_name is None:
            return None
        resource = self._resource_catalog.get(resource_name)
        return resource.resource_type if resource is not None else None

    def _deplete_nearest_claim(
        self,
        signal: ResourceDepletedSignal,
    ) -> MiningClaimDepletedEvent | None:
        position = self._position_provider()
        if position is None:
            logger.warning("claim_depleted_without_position event_dt=%s", signal.event_dt)
            return None

        nearest = self._nearest_active_claim(position)
        if nearest is None:
            logger.warning(
                "claim_depleted_without_nearby_claim position=%s event_dt=%s",
                position,
                signal.event_dt,
            )
            return None

        claim, distance_m = nearest
        del self._active_claims[claim.claim_id]
        event = MiningClaimDepletedEvent(
            claim_id=claim.claim_id,
            drop_id=claim.drop_id,
            hit_id=claim.hit_id,
            event_dt=signal.event_dt,
            position=position,
            distance_m=distance_m,
            raw=signal.raw,
            run_id=claim.run_id,
            segment_id=claim.segment_id,
        )
        logger.debug(
            "claim_depleted event_type=%s claim_id=%s distance_m=%.2f event_dt=%s",
            type(event).__name__,
            event.claim_id,
            event.distance_m,
            event.event_dt,
        )
        return event

    def _nearest_active_claim(self, position: WorldPos) -> tuple[ActiveClaim, float] | None:
        nearest: tuple[ActiveClaim, float] | None = None
        for claim in self._active_claims.values():
            if claim.position is None or not _same_planet(position, claim.position):
                continue
            distance_m = _distance_xy(position, claim.position)
            if distance_m > self._config.claim_depletion_link_max_distance_m:
                continue
            if nearest is None or distance_m < nearest[1]:
                nearest = (claim, distance_m)
        return nearest


def _none_position_provider() -> WorldPos | None:
    return None


def _same_planet(left: WorldPos, right: WorldPos) -> bool:
    if not left.planet_name or not right.planet_name:
        return True
    return left.planet_name == right.planet_name


def _distance_xy(left: WorldPos, right: WorldPos) -> float:
    return math.hypot(left.x - right.x, left.y - right.y)
