import type { components } from "@zml/api-contract";
import type { AgentEventEnvelope } from "./miningDrops";

export type MiningLootItemDto = {
    eventId: number;
    createdTsMs: number;
    eventDt: string | null;
    runId: number | null;
    segmentId: string | null;
    itemName: string;
    qty: number;
    valueMpec: number;
    extractionCostMpec: number | null;
};

export type MiningLootItemWire = components["schemas"]["MiningLootItemDto"];

export type MiningLootTotalDto = {
    scope: MiningLootTotalWire["scope"];
    runId: number;
    segmentId: string | null;
    itemName: string;
    qty: number;
    valueMpec: number;
    extractionCostMpec: number;
    eventCount: number;
    firstSeenTsMs: number;
    lastSeenTsMs: number;
};

export type MiningLootTotalWire = components["schemas"]["MiningLootTotalDto"];

export type MiningItemReceivedEventWire = {
    run_id?: number | null;
    segment_id?: string | null;
    item_name: string;
    qty: number;
    value_mpec: number;
    extraction_cost_mpec?: number | null;
};

export type MiningLootTotalsUpdatedEventWire = {
    updated_ts_ms: number;
    run_id?: number | null;
    segment_id?: string | null;
    recent_item?: MiningLootItemWire | null;
    run_total?: MiningLootTotalWire | null;
    segment_total?: MiningLootTotalWire | null;
};

export function isMiningLootItemWire(value: unknown): value is MiningLootItemWire {
    if (!isRecord(value)) return false;
    return (
        isFiniteNumber(value.event_id) &&
        isFiniteNumber(value.created_ts_ms) &&
        isNullableString(value.event_dt) &&
        isNullableNumber(value.run_id) &&
        isNullableString(value.segment_id) &&
        typeof value.item_name === "string" &&
        isFiniteNumber(value.qty) &&
        isFiniteNumber(value.value_mpec) &&
        isNullableNumber(value.extraction_cost_mpec)
    );
}

export function isMiningLootTotalWire(value: unknown): value is MiningLootTotalWire {
    if (!isRecord(value)) return false;
    return (
        (value.scope === "run" || value.scope === "segment") &&
        isFiniteNumber(value.run_id) &&
        isNullableString(value.segment_id) &&
        typeof value.item_name === "string" &&
        isFiniteNumber(value.qty) &&
        isFiniteNumber(value.value_mpec) &&
        isFiniteNumber(value.extraction_cost_mpec) &&
        isFiniteNumber(value.event_count) &&
        isFiniteNumber(value.first_seen_ts_ms) &&
        isFiniteNumber(value.last_seen_ts_ms)
    );
}

export function isMiningItemReceivedEventWire(value: unknown): value is MiningItemReceivedEventWire {
    if (!isRecord(value)) return false;
    return (
        (value.run_id === undefined || isNullableNumber(value.run_id)) &&
        (value.segment_id === undefined || isNullableString(value.segment_id)) &&
        typeof value.item_name === "string" &&
        isFiniteNumber(value.qty) &&
        isFiniteNumber(value.value_mpec) &&
        (value.extraction_cost_mpec === undefined || isNullableNumber(value.extraction_cost_mpec))
    );
}

export function isMiningLootTotalsUpdatedEventWire(
    value: unknown,
): value is MiningLootTotalsUpdatedEventWire {
    if (!isRecord(value)) return false;
    return (
        isFiniteNumber(value.updated_ts_ms) &&
        (value.run_id === undefined || isNullableNumber(value.run_id)) &&
        (value.segment_id === undefined || isNullableString(value.segment_id)) &&
        (value.recent_item === undefined ||
            value.recent_item === null ||
            isMiningLootItemWire(value.recent_item)) &&
        (value.run_total === undefined ||
            value.run_total === null ||
            isMiningLootTotalWire(value.run_total)) &&
        (value.segment_total === undefined ||
            value.segment_total === null ||
            isMiningLootTotalWire(value.segment_total))
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
        segmentId: wire.segment_id ?? null,
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
        segmentId: wire.segment_id,
        itemName: wire.item_name,
        qty: wire.qty,
        valueMpec: wire.value_mpec,
        extractionCostMpec: wire.extraction_cost_mpec,
    };
}

export function wireToMiningLootTotalDto(wire: MiningLootTotalWire): MiningLootTotalDto {
    return {
        scope: wire.scope,
        runId: wire.run_id,
        segmentId: wire.segment_id,
        itemName: wire.item_name,
        qty: wire.qty,
        valueMpec: wire.value_mpec,
        extractionCostMpec: wire.extraction_cost_mpec,
        eventCount: wire.event_count,
        firstSeenTsMs: wire.first_seen_ts_ms,
        lastSeenTsMs: wire.last_seen_ts_ms,
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
