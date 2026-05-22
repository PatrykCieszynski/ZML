import type { AgentEventEnvelope } from "./miningDrops";

export type MiningLootItemDto = {
    eventId: number;
    createdTsMs: number;
    eventDt: string | null;
    itemName: string;
    qty: number;
    valueMpec: number;
    extractionCostMpec: number | null;
};

export type MiningItemReceivedEventWire = {
    item_name: string;
    qty: number;
    value_mpec: number;
    extraction_cost_mpec?: number | null;
};

export function isMiningItemReceivedEventWire(value: unknown): value is MiningItemReceivedEventWire {
    if (!isRecord(value)) return false;
    return (
        typeof value.item_name === "string" &&
        isFiniteNumber(value.qty) &&
        isFiniteNumber(value.value_mpec) &&
        (value.extraction_cost_mpec === undefined || isNullableNumber(value.extraction_cost_mpec))
    );
}

export function miningLootItemDtoFromEventWire(
    wire: MiningItemReceivedEventWire,
    envelope: AgentEventEnvelope<string, unknown>,
): MiningLootItemDto {
    return {
        eventId: envelope.eventId ?? -1,
        createdTsMs: envelope.createdTsMs,
        eventDt: envelope.eventDt,
        itemName: wire.item_name,
        qty: wire.qty,
        valueMpec: wire.value_mpec,
        extractionCostMpec: wire.extraction_cost_mpec ?? null,
    };
}

function isNullableNumber(value: unknown): value is number | null {
    return value === null || isFiniteNumber(value);
}

function isFiniteNumber(value: unknown): value is number {
    return typeof value === "number" && Number.isFinite(value);
}

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === "object" && value !== null;
}
