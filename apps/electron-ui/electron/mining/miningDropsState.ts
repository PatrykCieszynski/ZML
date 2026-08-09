import {
    isMiningClaimCreatedEventWire,
    isMiningClaimDepletedEventWire,
    isMiningClaimExpiredEventWire,
    isMiningClaimIgnoredEventWire,
    isMiningClaimUpdatedEventWire,
    isMiningDropEventWire,
    isMiningHitHintEventWire,
    isMiningNoResourcesEventWire,
    miningClaimDtoFromCreatedEventWire,
    miningClaimDtoWithUpdatedEventWire,
    miningDropDtoFromMiningDropEventWire,
    miningDropDtoWithClaimCreated,
    miningDropDtoWithHitHint,
    miningDropDtoWithNoResources,
    type AgentEventEnvelope,
    type MiningClaimDepletedEventWire,
    type MiningClaimDto,
    type MiningClaimPositionDto,
    type MiningClaimPositionWire,
    type MiningDropDto,
} from "@desktop/shared";

import { pushStatePatch } from "../ipc/pushStatePatch.ts";
import { runtime } from "../runtime.ts";

export function replaceMiningClaims(claims: readonly MiningClaimDto[]): void {
    runtime.miningClaims = sortClaims([...claims]);
    pushStatePatch({ miningClaims: runtime.miningClaims });
}

export function replaceMiningDrops(drops: readonly MiningDropDto[]): void {
    runtime.miningDrops = sortDrops([...drops]);
    pushStatePatch({ miningDrops: runtime.miningDrops });
}

export function applyMiningEvent(event: AgentEventEnvelope<string, unknown>): void {
    if (event.type === "MiningDropEvent" && isMiningDropEventWire(event.payload)) {
        upsertMiningDrop(miningDropDtoFromMiningDropEventWire(event.payload, event.eventId));
        return;
    }

    if (event.type === "MiningHitHintEvent" && isMiningHitHintEventWire(event.payload)) {
        const payload = event.payload;
        updateMiningDrop(payload.drop_id, (drop) => miningDropDtoWithHitHint(drop, payload, event.eventId));
        return;
    }

    if (event.type === "MiningClaimCreatedEvent" && isMiningClaimCreatedEventWire(event.payload)) {
        const payload = event.payload;
        upsertMiningClaim(miningClaimDtoFromCreatedEventWire(payload, event.eventId));
        if (payload.drop_id !== null) {
            updateMiningDrop(payload.drop_id, (drop) =>
                miningDropDtoWithClaimCreated(drop, payload, event.eventId)
            );
        }
        return;
    }

    if (event.type === "MiningClaimUpdatedEvent" && isMiningClaimUpdatedEventWire(event.payload)) {
        const payload = event.payload;
        updateMiningClaim(payload.claim_id, (claim) =>
            miningClaimDtoWithUpdatedEventWire(claim, payload)
        );
        return;
    }

    if (event.type === "MiningClaimDepletedEvent" && isMiningClaimDepletedEventWire(event.payload)) {
        markMiningClaimDepleted(event.payload, event.eventId ?? null, event.eventDt);
        return;
    }

    if (event.type === "MiningClaimIgnoredEvent" && isMiningClaimIgnoredEventWire(event.payload)) {
        markMiningClaimIgnored(event.payload.claim_id);
        return;
    }

    if (event.type === "MiningClaimExpiredEvent" && isMiningClaimExpiredEventWire(event.payload)) {
        markMiningClaimExpired(event.payload.claim_id);
        return;
    }

    if (event.type === "MiningNoResourcesEvent" && isMiningNoResourcesEventWire(event.payload)) {
        const payload = event.payload;
        updateMiningDrop(payload.drop_id, (drop) => miningDropDtoWithNoResources(drop, payload, event.eventId));
    }
}

function upsertMiningClaim(claim: MiningClaimDto): void {
    const withoutCurrent = runtime.miningClaims.filter((item) => item.claimId !== claim.claimId);
    runtime.miningClaims = sortClaims([claim, ...withoutCurrent]);
    pushStatePatch({ miningClaims: runtime.miningClaims });
}

function updateMiningClaim(
    claimId: string,
    update: (claim: MiningClaimDto) => MiningClaimDto,
): void {
    let changed = false;
    runtime.miningClaims = runtime.miningClaims.map((claim) => {
        if (claim.claimId !== claimId) return claim;
        changed = true;
        return update(claim);
    });

    if (changed) {
        runtime.miningClaims = sortClaims(runtime.miningClaims);
        pushStatePatch({ miningClaims: runtime.miningClaims });
    }
}

function markMiningClaimDepleted(
    payload: MiningClaimDepletedEventWire,
    eventId: number | null,
    eventDt: string | null,
): void {
    const hasClaim = runtime.miningClaims.some((claim) => claim.claimId === payload.claim_id);
    if (!hasClaim) return;

    runtime.miningClaims = sortClaims(runtime.miningClaims.map((claim) => {
        if (claim.claimId !== payload.claim_id) return claim;
        return {
            ...claim,
            status: "depleted",
            depletedEventId: eventId,
            depletedEventDt: eventDt,
            depletedPosition: wireToClaimPosition(payload.position),
            depletedDistanceM: payload.distance_m,
        };
    }));
    pushStatePatch({ miningClaims: runtime.miningClaims });
}

function markMiningClaimIgnored(claimId: string): void {
    const hasClaim = runtime.miningClaims.some((claim) => claim.claimId === claimId);
    if (!hasClaim) return;

    runtime.miningClaims = sortClaims(runtime.miningClaims.map((claim) => {
        if (claim.claimId !== claimId) return claim;
        return {
            ...claim,
            status: "ignored",
        };
    }));
    pushStatePatch({ miningClaims: runtime.miningClaims });
}

function markMiningClaimExpired(claimId: string): void {
    const hasClaim = runtime.miningClaims.some((claim) => claim.claimId === claimId);
    if (!hasClaim) return;

    runtime.miningClaims = sortClaims(runtime.miningClaims.map((claim) => {
        if (claim.claimId !== claimId) return claim;
        return {
            ...claim,
            status: "expired",
        };
    }));
    pushStatePatch({ miningClaims: runtime.miningClaims });
}

function upsertMiningDrop(drop: MiningDropDto): void {
    const withoutCurrent = runtime.miningDrops.filter((item) => item.dropId !== drop.dropId);
    runtime.miningDrops = sortDrops([drop, ...withoutCurrent]);
    pushStatePatch({ miningDrops: runtime.miningDrops });
}

function updateMiningDrop(
    dropId: string,
    update: (drop: MiningDropDto) => MiningDropDto,
): void {
    let changed = false;
    runtime.miningDrops = runtime.miningDrops.map((drop) => {
        if (drop.dropId !== dropId) return drop;
        changed = true;
        return update(drop);
    });

    if (changed) {
        runtime.miningDrops = sortDrops(runtime.miningDrops);
        pushStatePatch({ miningDrops: runtime.miningDrops });
    }
}

function sortDrops(drops: MiningDropDto[]): MiningDropDto[] {
    return drops.sort((a, b) => b.observedTsMs - a.observedTsMs);
}

function sortClaims(claims: MiningClaimDto[]): MiningClaimDto[] {
    return claims.sort((a, b) => b.observedTsMs - a.observedTsMs);
}

function wireToClaimPosition(wire: MiningClaimPositionWire): MiningClaimPositionDto {
    return {
        planetName: wire.planet_name ?? "",
        x: wire.x,
        y: wire.y,
        z: wire.z ?? null,
    };
}
