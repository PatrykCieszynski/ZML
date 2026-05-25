import {
    isMiningClaimCreatedEventWire,
    isMiningClaimDepletedEventWire,
    isMiningDropEventWire,
    isMiningHitHintEventWire,
    isMiningNoResourcesEventWire,
    miningClaimDtoFromCreatedEventWire,
    miningDropDtoFromMiningDropEventWire,
    miningDropDtoWithHitHint,
    miningDropDtoWithNoResources,
    type AgentEventEnvelope,
    type MiningClaimDto,
    type MiningDropDto,
} from "@zml/shared";

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
        upsertMiningClaim(miningClaimDtoFromCreatedEventWire(event.payload, event.eventId));
        return;
    }

    if (event.type === "MiningClaimDepletedEvent" && isMiningClaimDepletedEventWire(event.payload)) {
        removeMiningClaim({
            claimId: event.payload.claim_id,
            dropId: event.payload.drop_id,
            hitId: event.payload.hit_id,
        });
        return;
    }

    if (event.type === "MiningNoResourcesEvent" && isMiningNoResourcesEventWire(event.payload)) {
        const payload = event.payload;
        updateMiningDrop(payload.drop_id, (drop) => miningDropDtoWithNoResources(drop, payload, event.eventId));
    }
}

function upsertMiningClaim(claim: MiningClaimDto): void {
    if (claim.status !== "active") return;
    const withoutCurrent = runtime.miningClaims.filter((item) => item.claimId !== claim.claimId);
    runtime.miningClaims = sortClaims([claim, ...withoutCurrent]);
    pushStatePatch({ miningClaims: runtime.miningClaims });
}

function removeMiningClaim({
    claimId,
    dropId,
    hitId,
}: {
    claimId: string;
    dropId: string | null;
    hitId: string | null;
}): void {
    const nextClaims = runtime.miningClaims.filter((claim) => {
        if (claim.claimId === claimId) return false;
        if (dropId !== null && claim.dropId === dropId) return false;
        if (hitId !== null && claim.hitId === hitId) return false;
        return true;
    });
    if (nextClaims.length === runtime.miningClaims.length) return;
    runtime.miningClaims = nextClaims;
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
    return claims
        .filter((claim) => claim.status === "active")
        .sort((a, b) => b.observedTsMs - a.observedTsMs);
}
