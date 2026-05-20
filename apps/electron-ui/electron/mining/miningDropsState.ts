import {
    isMiningDropEventWire,
    isMiningHitHintEventWire,
    isMiningNoResourcesEventWire,
    miningDropDtoFromMiningDropEventWire,
    miningDropDtoWithHitHint,
    miningDropDtoWithNoResources,
    type AgentEventEnvelope,
    type MiningDropDto,
} from "@zml/shared";

import { pushStatePatch } from "../ipc/pushStatePatch.ts";
import { runtime } from "../runtime.ts";

const MINING_DROP_WINDOW_MS = 30 * 60_000;

export function replaceMiningDrops(drops: readonly MiningDropDto[]): void {
    runtime.miningDrops = sortAndTrimDrops([...drops]);
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

    if (event.type === "MiningNoResourcesEvent" && isMiningNoResourcesEventWire(event.payload)) {
        const payload = event.payload;
        updateMiningDrop(payload.drop_id, (drop) => miningDropDtoWithNoResources(drop, payload, event.eventId));
    }
}

function upsertMiningDrop(drop: MiningDropDto): void {
    const withoutCurrent = runtime.miningDrops.filter((item) => item.dropId !== drop.dropId);
    runtime.miningDrops = sortAndTrimDrops([drop, ...withoutCurrent]);
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
        runtime.miningDrops = sortAndTrimDrops(runtime.miningDrops);
        pushStatePatch({ miningDrops: runtime.miningDrops });
    }
}

function sortAndTrimDrops(drops: MiningDropDto[]): MiningDropDto[] {
    const cutoff = Date.now() - MINING_DROP_WINDOW_MS;
    return drops
        .filter((drop) => drop.observedTsMs >= cutoff)
        .sort((a, b) => b.observedTsMs - a.observedTsMs);
}
