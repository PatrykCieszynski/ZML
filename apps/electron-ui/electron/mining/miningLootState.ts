import {
    isMiningItemReceivedEventWire,
    miningLootItemDtoFromEventWire,
    type AgentEventEnvelope,
    type MiningLootItemDto,
} from "@zml/shared";

import { pushStatePatch } from "../ipc/pushStatePatch.ts";
import { runtime } from "../runtime.ts";

const MAX_LOOT_ITEMS = 500;

export function replaceMiningLoot(items: readonly MiningLootItemDto[]): void {
    runtime.miningLoot = sortLootItems([...items]);
    pushStatePatch({ miningLoot: runtime.miningLoot });
}

export function applyMiningLootEvent(event: AgentEventEnvelope<string, unknown>): void {
    if (event.type !== "MiningItemReceivedEvent" || !isMiningItemReceivedEventWire(event.payload)) {
        return;
    }
    upsertLootItem(miningLootItemDtoFromEventWire(event.payload, event));
}

function upsertLootItem(item: MiningLootItemDto): void {
    const withoutCurrent = runtime.miningLoot.filter((current) => current.eventId !== item.eventId);
    runtime.miningLoot = sortLootItems([item, ...withoutCurrent]).slice(0, MAX_LOOT_ITEMS);
    pushStatePatch({ miningLoot: runtime.miningLoot });
}

function sortLootItems(items: MiningLootItemDto[]): MiningLootItemDto[] {
    return items.sort((a, b) => b.createdTsMs - a.createdTsMs || b.eventId - a.eventId);
}
