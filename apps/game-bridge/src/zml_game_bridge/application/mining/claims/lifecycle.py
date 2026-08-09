from __future__ import annotations

import logging
import math
from collections.abc import Iterable
from dataclasses import dataclass

from zml_game_bridge.application.mining.claims.commands import (
    ExpireMiningClaimsCommand,
    IgnoreMiningClaimCommand,
    MarkMiningClaimDepletedCommand,
    ResolvePendingDropResultsCommand,
)
from zml_game_bridge.application.mining.settings import IdFactory, MiningCoordinatorConfig
from zml_game_bridge.application.position.provider import PositionProvider
from zml_game_bridge.domain.mining_events import (
    MiningClaimCreatedEvent,
    MiningClaimDeedReceivedEvent,
    MiningClaimDepletedEvent,
    MiningClaimExpiredEvent,
    MiningClaimIgnoredEvent,
    MiningClaimUpdatedEvent,
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
    expected_expires_ts_ms: int | None
    observed_ts_ms: int | None = None
    resource_name: str | None = None
    mining_type: str | None = None


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
        self._claim_ids_by_drop_id: dict[str, str] = {}

    def restore_active_claims(self, claims: Iterable[ActiveClaim]) -> None:
        self._active_claims = {claim.claim_id: claim for claim in claims}
        self._claim_ids_by_drop_id = {
            claim.drop_id: claim.claim_id
            for claim in self._active_claims.values()
            if claim.drop_id is not None
        }
        logger.info("claim_lifecycle_restored active_claims=%s", len(self._active_claims))

    def process_event(self, event: EventBase) -> list[EventBase]:
        if isinstance(event, MiningDropEvent):
            stale_results = self._resolve_stale_pending_drops(event.observed_ts_ms)
            self._drops_by_id[event.drop_id] = event
            return stale_results

        if isinstance(event, MiningHitHintEvent):
            created = self._create_claim_from_hit_hint(event)
            return [created] if created is not None else []

        if isinstance(event, MiningClaimDeedReceivedEvent):
            resolved = self._merge_claim_deed(event)
            return [resolved] if resolved is not None else []

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

    def expire_claims(self, command: ExpireMiningClaimsCommand) -> list[MiningClaimExpiredEvent]:
        events: list[MiningClaimExpiredEvent] = []
        for claim in list(self._active_claims.values()):
            expected_expires_ts_ms = claim.expected_expires_ts_ms
            if expected_expires_ts_ms is None or expected_expires_ts_ms > command.now_ts_ms:
                continue

            del self._active_claims[claim.claim_id]
            events.append(
                MiningClaimExpiredEvent(
                    claim_id=claim.claim_id,
                    expired_ts_ms=command.now_ts_ms,
                    expected_expires_ts_ms=expected_expires_ts_ms,
                    drop_id=claim.drop_id,
                    hit_id=claim.hit_id,
                    run_id=claim.run_id,
                    segment_id=claim.segment_id,
                )
            )

        if events:
            logger.info(
                "claim_lifecycle_expired_claims count=%s now_ts_ms=%s",
                len(events),
                command.now_ts_ms,
            )
        return events

    def resolve_pending_drop_results(
        self,
        command: ResolvePendingDropResultsCommand,
    ) -> list[MiningNoResourcesEvent]:
        events = self._resolve_stale_pending_drops(command.now_ts_ms)
        if events:
            logger.info(
                "claim_lifecycle_resolved_pending_drops count=%s now_ts_ms=%s",
                len(events),
                command.now_ts_ms,
            )
        return events

    def _create_claim_from_hit_hint(
        self,
        event: MiningHitHintEvent,
    ) -> MiningClaimCreatedEvent | MiningClaimUpdatedEvent | None:
        drop = self._drops_by_id.get(event.drop_id) if event.drop_id is not None else None
        if event.drop_id is not None:
            # TODO: Multi-mode drops can produce multiple claim deeds for one drop.
            # Keep this cache entry for the full correlation window once deed OCR/chat
            # claim correlation can create more than one claim from the same drop.
            self._drops_by_id.pop(event.drop_id, None)
            existing_claim_id = self._claim_ids_by_drop_id.get(event.drop_id)
            if existing_claim_id is not None:
                return self._update_claim_from_hit_hint(existing_claim_id, event, drop)
        claim_id = self._id_factory()
        position = event.position if event.position is not None else drop.position if drop else None
        search_radius_m = drop.drop_radius_m if drop is not None else None
        run_id = drop.run_id if drop is not None else event.run_id
        segment_id = drop.segment_id if drop is not None else event.segment_id

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
            expected_expires_ts_ms=event.expected_expires_ts_ms,
            observed_ts_ms=event.observed_ts_ms,
            resource_name=event.resource_name,
            mining_type=created.mining_type,
        )
        if event.drop_id is not None:
            self._claim_ids_by_drop_id[event.drop_id] = claim_id
        logger.debug(
            "claim_created event_type=%s claim_id=%s hit_id=%s drop_id=%s resource=%r",
            type(created).__name__,
            created.claim_id,
            created.hit_id,
            created.drop_id,
            created.resource_name,
        )
        return created

    def _update_claim_from_hit_hint(
        self,
        claim_id: str,
        event: MiningHitHintEvent,
        drop: MiningDropEvent | None,
    ) -> MiningClaimUpdatedEvent:
        run_id = drop.run_id if drop is not None else event.run_id
        segment_id = drop.segment_id if drop is not None else event.segment_id
        updated = MiningClaimUpdatedEvent(
            claim_id=claim_id,
            updated_ts_ms=event.observed_ts_ms,
            hit_id=event.hit_id,
            drop_id=event.drop_id,
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
        claim = self._active_claims.get(claim_id)
        if claim is not None:
            claim.hit_id = event.hit_id
            claim.expected_expires_ts_ms = event.expected_expires_ts_ms
            claim.resource_name = event.resource_name
            claim.mining_type = updated.mining_type
        logger.debug(
            "claim_updated_from_hit_hint event_type=%s claim_id=%s hit_id=%s drop_id=%s resource=%r",
            type(updated).__name__,
            updated.claim_id,
            updated.hit_id,
            updated.drop_id,
            updated.resource_name,
        )
        return updated

    def _merge_claim_deed(
        self,
        event: MiningClaimDeedReceivedEvent,
    ) -> MiningClaimCreatedEvent | MiningClaimUpdatedEvent | None:
        drop = self._latest_unclaimed_drop_for_deed(event)
        if drop is not None:
            return self._create_claim_from_deed(event, drop)

        claim = self._latest_claim_for_deed(event)
        if claim is not None:
            return self._update_claim_from_deed(claim, event)

        logger.warning(
            "claim_deed_without_pending_drop resource=%r mining_type=%s run_id=%s segment_id=%s",
            event.resource_name,
            event.mining_type,
            event.run_id,
            event.segment_id,
        )
        return None

    def _create_claim_from_deed(
        self,
        event: MiningClaimDeedReceivedEvent,
        drop: MiningDropEvent,
    ) -> MiningClaimCreatedEvent:
        self._drops_by_id.pop(drop.drop_id, None)
        claim_id = self._id_factory()
        created = MiningClaimCreatedEvent(
            claim_id=claim_id,
            hit_id=None,
            drop_id=drop.drop_id,
            observed_ts_ms=drop.observed_ts_ms,
            position=drop.position,
            search_radius_m=drop.drop_radius_m,
            resource_name=event.resource_name,
            mining_type=event.mining_type,
            size_label=None,
            size_index=None,
            expected_expires_ts_ms=None,
            range_m=None,
            depth_m=None,
            run_id=drop.run_id if drop.run_id is not None else event.run_id,
            segment_id=drop.segment_id if drop.segment_id is not None else event.segment_id,
        )
        self._active_claims[claim_id] = ActiveClaim(
            claim_id=claim_id,
            drop_id=drop.drop_id,
            hit_id=None,
            run_id=created.run_id,
            segment_id=created.segment_id,
            position=created.position,
            search_radius_m=created.search_radius_m,
            expected_expires_ts_ms=None,
            observed_ts_ms=created.observed_ts_ms,
            resource_name=created.resource_name,
            mining_type=created.mining_type,
        )
        self._claim_ids_by_drop_id[drop.drop_id] = claim_id
        logger.debug(
            "claim_created_from_deed event_type=%s claim_id=%s drop_id=%s resource=%r",
            type(created).__name__,
            created.claim_id,
            created.drop_id,
            created.resource_name,
        )
        return created

    def _update_claim_from_deed(
        self,
        claim: ActiveClaim,
        event: MiningClaimDeedReceivedEvent,
    ) -> MiningClaimUpdatedEvent:
        updated = MiningClaimUpdatedEvent(
            claim_id=claim.claim_id,
            updated_ts_ms=claim.observed_ts_ms or 0,
            hit_id=claim.hit_id,
            drop_id=claim.drop_id,
            resource_name=event.resource_name,
            mining_type=event.mining_type,
            run_id=claim.run_id if claim.run_id is not None else event.run_id,
            segment_id=claim.segment_id if claim.segment_id is not None else event.segment_id,
        )
        claim.resource_name = event.resource_name
        claim.mining_type = event.mining_type
        logger.debug(
            "claim_updated_from_deed event_type=%s claim_id=%s drop_id=%s resource=%r mining_type=%s",
            type(updated).__name__,
            updated.claim_id,
            updated.drop_id,
            updated.resource_name,
            updated.mining_type,
        )
        return updated

    def _latest_unclaimed_drop_for_deed(
        self,
        event: MiningClaimDeedReceivedEvent,
    ) -> MiningDropEvent | None:
        candidates = [
            drop
            for drop in self._drops_by_id.values()
            if drop.drop_id not in self._claim_ids_by_drop_id and _same_context(drop, event)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda drop: drop.observed_ts_ms)

    def _latest_claim_for_deed(
        self,
        event: MiningClaimDeedReceivedEvent,
    ) -> ActiveClaim | None:
        candidates = [
            claim
            for claim in self._active_claims.values()
            if claim.drop_id is not None
            and _same_claim_context(claim, event)
            and _same_or_missing_resource(claim.resource_name, event.resource_name)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda claim: claim.observed_ts_ms or 0)

    def _resolve_stale_pending_drops(self, now_ts_ms: int) -> list[MiningNoResourcesEvent]:
        stale_drop_ids = [
            drop_id
            for drop_id, drop in self._drops_by_id.items()
            if now_ts_ms - drop.observed_ts_ms >= self._config.result_link_window_ms
        ]
        events: list[MiningNoResourcesEvent] = []
        for drop_id in stale_drop_ids:
            drop = self._drops_by_id.pop(drop_id)
            if drop_id in self._claim_ids_by_drop_id:
                continue
            events.append(
                MiningNoResourcesEvent(
                    drop_id=drop.drop_id,
                    observed_ts_ms=now_ts_ms,
                    position=drop.position,
                    raw_status_text="Auto-resolved after missing finder/chat result",
                    run_id=drop.run_id,
                    segment_id=drop.segment_id,
                )
            )
        if stale_drop_ids:
            logger.debug(
                "claim_lifecycle_checked_stale_drops stale_count=%s resolved_count=%s",
                len(stale_drop_ids),
                len(events),
            )
        return events

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


def _same_context(drop: MiningDropEvent, deed: MiningClaimDeedReceivedEvent) -> bool:
    if drop.run_id is not None and deed.run_id is not None and drop.run_id != deed.run_id:
        return False
    return not (
        drop.segment_id is not None
        and deed.segment_id is not None
        and drop.segment_id != deed.segment_id
    )


def _same_claim_context(claim: ActiveClaim, deed: MiningClaimDeedReceivedEvent) -> bool:
    if claim.run_id is not None and deed.run_id is not None and claim.run_id != deed.run_id:
        return False
    return not (
        claim.segment_id is not None
        and deed.segment_id is not None
        and claim.segment_id != deed.segment_id
    )


def _same_or_missing_resource(left: str | None, right: str | None) -> bool:
    if left is None or right is None:
        return True
    return " ".join(left.lower().split()) == " ".join(right.lower().split())
