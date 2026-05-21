import {
    isMiningItemReceivedEventWire,
    miningLootItemDtoFromEventWire,
    type AgentEventEnvelope,
    type MiningLootItemDto,
} from "@zml/shared";

import { pushStatePatch } from "../ipc/pushStatePatch.ts";
import { runtime } from "../runtime.ts";

const MAX_LOOT_ITEMS = 500;

export function applyMiningLootEvent(event: AgentEventEnvelope<string, unknown>): void {
    if (event.type !== "MiningItemReceivedEvent" || !isMiningItemReceivedEventWire(event.payload)) {
        return;
    }
    upsertLootItem(miningLootItemDtoFromEventWire(event.payload, event));
}

function upsertLootItem(item: MiningLootItemDto): void {
    const withoutCurrent = runtime.miningLoot.filter((current) => current.eventId !== item.eventId);
    runtime.miningLoot = [item, ...withoutCurrent]
        .sort((a, b) => b.createdTsMs - a.createdTsMs)
        .slice(0, MAX_LOOT_ITEMS);
    pushStatePatch({ miningLoot: runtime.miningLoot });
}
