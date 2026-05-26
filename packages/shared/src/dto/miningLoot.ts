import type { AgentEventEnvelope } from "./miningDrops";

export type MiningLootItemDto = {
    eventId: number;
    createdTsMs: number;
    eventDt: string | null;
    runId: number | null;
    itemName: string;
    qty: number;
    valueMpec: number;
    extractionCostMpec: number | null;
};

export type MiningLootItemWire = {
    event_id: number;
    created_ts_ms: number;
    event_dt: string | null;
    run_id: number | null;
    item_name: string;
    qty: number;
    value_mpec: number;
    extraction_cost_mpec: number | null;
};

export type MiningItemReceivedEventWire = {
    run_id?: number | null;
    item_name: string;
    qty: number;
    value_mpec: number;
    extraction_cost_mpec?: number | null;
};

export function isMiningLootItemWire(value: unknown): value is MiningLootItemWire {
    if (!isRecord(value)) return false;
    return (
        isFiniteNumber(value.event_id) &&
        isFiniteNumber(value.created_ts_ms) &&
        isNullableString(value.event_dt) &&
        isNullableNumber(value.run_id) &&
        typeof value.item_name === "string" &&
        isFiniteNumber(value.qty) &&
        isFiniteNumber(value.value_mpec) &&
        isNullableNumber(value.extraction_cost_mpec)
    );
}

export function isMiningItemReceivedEventWire(value: unknown): value is MiningItemReceivedEventWire {
    if (!isRecord(value)) return false;
    return (
        (value.run_id === undefined || isNullableNumber(value.run_id)) &&
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
        runId: wire.run_id ?? null,
        itemName: wire.item_name,
        qty: wire.qty,
        valueMpec: wire.value_mpec,
        extractionCostMpec: wire.extraction_cost_mpec ?? null,
    };
}

export function wireToMiningLootItemDto(wire: MiningLootItemWire): MiningLootItemDto {
    return {
        eventId: wire.event_id,
        createdTsMs: wire.created_ts_ms,
        eventDt: wire.event_dt,
        runId: wire.run_id,
        itemName: wire.item_name,
        qty: wire.qty,
        valueMpec: wire.value_mpec,
        extractionCostMpec: wire.extraction_cost_mpec,
    };
}

function isNullableNumber(value: unknown): value is number | null {
    return value === null || isFiniteNumber(value);
}

function isNullableString(value: unknown): value is string | null {
    return value === null || typeof value === "string";
}

function isFiniteNumber(value: unknown): value is number {
    return typeof value === "number" && Number.isFinite(value);
}

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === "object" && value !== null;
}
