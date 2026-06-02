import {
    isMiningItemReceivedEventWire,
    isMiningLootTotalsUpdatedEventWire,
    miningLootItemDtoFromEventWire,
    type AgentEventEnvelope,
    type MiningLootItemDto,
    type MiningLootTotalDto,
    wireToMiningLootItemDto,
    wireToMiningLootTotalDto,
} from "@zml/shared";

import { pushStatePatch } from "../ipc/pushStatePatch.ts";
import { runtime } from "../runtime.ts";

const MAX_LOOT_ITEMS = 25;

export function replaceMiningLoot(items: readonly MiningLootItemDto[]): void {
    runtime.miningLoot = sortLootItems([...items]);
    pushStatePatch({ miningLoot: runtime.miningLoot });
}

export function replaceMiningLootTotals(items: readonly MiningLootTotalDto[]): void {
    runtime.miningLootTotals = sortLootTotals([...items]);
    pushStatePatch({ miningLootTotals: runtime.miningLootTotals });
}

export function applyMiningLootEvent(event: AgentEventEnvelope<string, unknown>): void {
    if (event.type === "MiningLootTotalsUpdatedEvent" && isMiningLootTotalsUpdatedEventWire(event.payload)) {
        const nextLoot = event.payload.recent_item
            ? upsertLootItemValue(runtime.miningLoot, wireToMiningLootItemDto(event.payload.recent_item))
            : runtime.miningLoot;
        let nextTotals = runtime.miningLootTotals;
        if (event.payload.run_total) {
            nextTotals = upsertLootTotalValue(nextTotals, wireToMiningLootTotalDto(event.payload.run_total));
        }
        if (event.payload.segment_total) {
            nextTotals = upsertLootTotalValue(nextTotals, wireToMiningLootTotalDto(event.payload.segment_total));
        }
        runtime.miningLoot = nextLoot;
        runtime.miningLootTotals = sortLootTotals(nextTotals);
        pushStatePatch({
            miningLoot: runtime.miningLoot,
            miningLootTotals: runtime.miningLootTotals,
        });
        return;
    }

    if (event.type === "MiningItemReceivedEvent" && isMiningItemReceivedEventWire(event.payload)) {
        upsertLootItem(miningLootItemDtoFromEventWire(event.payload, event));
    }
}

function upsertLootItem(item: MiningLootItemDto): void {
    runtime.miningLoot = upsertLootItemValue(runtime.miningLoot, item);
    pushStatePatch({ miningLoot: runtime.miningLoot });
}

function upsertLootItemValue(items: readonly MiningLootItemDto[], item: MiningLootItemDto): MiningLootItemDto[] {
    const withoutCurrent = items.filter((current) => current.eventId !== item.eventId);
    return sortLootItems([item, ...withoutCurrent]).slice(0, MAX_LOOT_ITEMS);
}

function upsertLootTotalValue(items: readonly MiningLootTotalDto[], item: MiningLootTotalDto): MiningLootTotalDto[] {
    const withoutCurrent = items.filter(
        (current) =>
            current.scope !== item.scope ||
            current.runId !== item.runId ||
            current.segmentId !== item.segmentId ||
            current.itemName !== item.itemName,
    );
    return [...withoutCurrent, item];
}

function sortLootItems(items: MiningLootItemDto[]): MiningLootItemDto[] {
    return items.sort((a, b) => b.createdTsMs - a.createdTsMs || b.eventId - a.eventId);
}

function sortLootTotals(items: MiningLootTotalDto[]): MiningLootTotalDto[] {
    return items.sort((a, b) => b.valueMpec - a.valueMpec || a.itemName.localeCompare(b.itemName));
}
