import type { WorldPosDTO } from "./worldPos";
import type { MiningClaimCreatedEventWire } from "./miningClaims";

export type MiningDropResult = "pending" | "hit" | "no_resources";

export type MiningDropPositionDto = WorldPosDTO;

export type MiningDropCostDto = {
    ammoCostMpec: number;
    probesCostMpec: number;
    finderDecayMpec: number;
    finderEnhancerDecayMpec: number;
    ampDecayMpec: number;
    totalTtMpec: number;
    totalWithMarkupMpec: number;
};

export type MiningDropDto = {
    dropId: string;
    dropEventId: number;
    runId: number | null;
    segmentId: string | null;
    observedTsMs: number;
    position: MiningDropPositionDto | null;
    dropRadiusM: number;
    modesMask: number | null;
    probesPerDrop: number | null;
    ammoPerDrop: number | null;
    cost: MiningDropCostDto;
    result: MiningDropResult;
    resultEventId: number | null;
    resultObservedTsMs: number | null;
    hitId: string | null;
    hitEventId: number | null;
    resourceName: string | null;
    sizeLabel: string | null;
    sizeIndex: number | null;
    expectedExpiresTsMs: number | null;
    rangeM: number | null;
    depthM: number | null;
};

export type MiningDropPositionWire = {
    planet_name: string | null;
    x: number;
    y: number;
    z?: number | null;
};

export type MiningDropCostWire = {
    ammo_cost_mpec: number;
    probes_cost_mpec: number;
    finder_decay_mpec: number;
    finder_enhancer_decay_mpec: number;
    amp_decay_mpec: number;
    total_tt_mpec: number;
    total_with_markup_mpec: number;
};

export type MiningDropWire = {
    drop_id: string;
    drop_event_id: number;
    run_id?: number | null;
    segment_id?: string | null;
    observed_ts_ms: number;
    position: MiningDropPositionWire | null;
    drop_radius_m: number;
    modes_mask: number | null;
    probes_per_drop: number | null;
    ammo_per_drop: number | null;
    cost: MiningDropCostWire;
    result: MiningDropResult;
    result_event_id: number | null;
    result_observed_ts_ms: number | null;
    hit_id: string | null;
    hit_event_id: number | null;
    resource_name: string | null;
    size_label: string | null;
    size_index: number | null;
    expected_expires_ts_ms: number | null;
    range_m: number | null;
    depth_m: number | null;
};

type MiningDropEventCostComponentWire = {
    quantity: number | null;
    cost_mpec: number;
    source: string;
};

type MiningDropEventCostWire = {
    ammo: MiningDropEventCostComponentWire;
    probes: MiningDropEventCostComponentWire;
    finder_decay_mpec: number;
    finder_enhancer_decay_mpec?: number;
    amp_decay_mpec: number;
    total_tt_mpec: number;
    total_with_markup_mpec: number;
};

export type MiningDropEventWire = {
    drop_id: string;
    run_id?: number | null;
    segment_id?: string | null;
    observed_ts_ms: number;
    position: MiningDropPositionWire | null;
    drop_radius_m: number;
    modes_mask: number | null;
    probes_per_drop: number | null;
    ammo_per_drop: number | null;
    cost: MiningDropEventCostWire;
    raw_status_text?: string | null;
};

export type MiningHitHintEventWire = {
    hit_id: string;
    drop_id: string;
    observed_ts_ms: number;
    position: MiningDropPositionWire | null;
    size_label: string | null;
    size_index: number | null;
    resource_name: string | null;
    expected_expires_ts_ms?: number | null;
    range_m: number | null;
    depth_m: number | null;
};

export type MiningNoResourcesEventWire = {
    drop_id: string;
    observed_ts_ms: number;
    position: MiningDropPositionWire | null;
};

export type AgentEventEnvelope<TType extends string, TPayload> = {
    type: TType;
    eventId?: number;
    createdTsMs: number;
    eventDt: string | null;
    payload: TPayload;
};

export function isMiningDropWire(value: unknown): value is MiningDropWire {
    if (!isRecord(value)) return false;
    return (
        typeof value.drop_id === "string" &&
        isFiniteNumber(value.drop_event_id) &&
        (value.run_id === undefined || isNullableNumber(value.run_id)) &&
        (value.segment_id === undefined || isNullableString(value.segment_id)) &&
        isFiniteNumber(value.observed_ts_ms) &&
        isNullablePositionWire(value.position) &&
        isFiniteNumber(value.drop_radius_m) &&
        isNullableNumber(value.modes_mask) &&
        isNullableNumber(value.probes_per_drop) &&
        isNullableNumber(value.ammo_per_drop) &&
        isMiningDropCostWire(value.cost) &&
        isMiningDropResult(value.result) &&
        isNullableNumber(value.result_event_id) &&
        isNullableNumber(value.result_observed_ts_ms) &&
        isNullableString(value.hit_id) &&
        isNullableNumber(value.hit_event_id) &&
        isNullableString(value.resource_name) &&
        isNullableString(value.size_label) &&
        isNullableNumber(value.size_index) &&
        isNullableNumber(value.expected_expires_ts_ms) &&
        isNullableNumber(value.range_m) &&
        isNullableNumber(value.depth_m)
    );
}

export function isMiningDropEventWire(value: unknown): value is MiningDropEventWire {
    if (!isRecord(value)) return false;
    return (
        typeof value.drop_id === "string" &&
        (value.run_id === undefined || isNullableNumber(value.run_id)) &&
        (value.segment_id === undefined || isNullableString(value.segment_id)) &&
        isFiniteNumber(value.observed_ts_ms) &&
        isNullablePositionWire(value.position) &&
        isFiniteNumber(value.drop_radius_m) &&
        isNullableNumber(value.modes_mask) &&
        isNullableNumber(value.probes_per_drop) &&
        isNullableNumber(value.ammo_per_drop) &&
        isMiningDropEventCostWire(value.cost)
    );
}

export function isMiningHitHintEventWire(value: unknown): value is MiningHitHintEventWire {
    if (!isRecord(value)) return false;
    return (
        typeof value.hit_id === "string" &&
        typeof value.drop_id === "string" &&
        isFiniteNumber(value.observed_ts_ms) &&
        isNullablePositionWire(value.position) &&
        isNullableString(value.size_label) &&
        isNullableNumber(value.size_index) &&
        isNullableString(value.resource_name) &&
        (value.expected_expires_ts_ms === undefined ||
            isNullableNumber(value.expected_expires_ts_ms)) &&
        isNullableNumber(value.range_m) &&
        isNullableNumber(value.depth_m)
    );
}

export function isMiningNoResourcesEventWire(value: unknown): value is MiningNoResourcesEventWire {
    if (!isRecord(value)) return false;
    return (
        typeof value.drop_id === "string" &&
        isFiniteNumber(value.observed_ts_ms) &&
        isNullablePositionWire(value.position)
    );
}

export function wireToMiningDropDto(wire: MiningDropWire): MiningDropDto {
    return {
        dropId: wire.drop_id,
        dropEventId: wire.drop_event_id,
        runId: wire.run_id ?? null,
        segmentId: wire.segment_id ?? null,
        observedTsMs: wire.observed_ts_ms,
        position: wire.position ? wireToPositionDto(wire.position) : null,
        dropRadiusM: wire.drop_radius_m,
        modesMask: wire.modes_mask,
        probesPerDrop: wire.probes_per_drop,
        ammoPerDrop: wire.ammo_per_drop,
        cost: {
            ammoCostMpec: wire.cost.ammo_cost_mpec,
            probesCostMpec: wire.cost.probes_cost_mpec,
            finderDecayMpec: wire.cost.finder_decay_mpec,
            finderEnhancerDecayMpec: wire.cost.finder_enhancer_decay_mpec,
            ampDecayMpec: wire.cost.amp_decay_mpec,
            totalTtMpec: wire.cost.total_tt_mpec,
            totalWithMarkupMpec: wire.cost.total_with_markup_mpec,
        },
        result: wire.result,
        resultEventId: wire.result_event_id,
        resultObservedTsMs: wire.result_observed_ts_ms,
        hitId: wire.hit_id,
        hitEventId: wire.hit_event_id,
        resourceName: wire.resource_name,
        sizeLabel: wire.size_label,
        sizeIndex: wire.size_index,
        expectedExpiresTsMs: wire.expected_expires_ts_ms,
        rangeM: wire.range_m,
        depthM: wire.depth_m,
    };
}

export function miningDropDtoFromMiningDropEventWire(
    wire: MiningDropEventWire,
    eventId: number = -1,
): MiningDropDto {
    return {
        dropId: wire.drop_id,
        dropEventId: eventId,
        runId: wire.run_id ?? null,
        segmentId: wire.segment_id ?? null,
        observedTsMs: wire.observed_ts_ms,
        position: wire.position ? wireToPositionDto(wire.position) : null,
        dropRadiusM: wire.drop_radius_m,
        modesMask: wire.modes_mask,
        probesPerDrop: wire.probes_per_drop,
        ammoPerDrop: wire.ammo_per_drop,
        cost: {
            ammoCostMpec: wire.cost.ammo.cost_mpec,
            probesCostMpec: wire.cost.probes.cost_mpec,
            finderDecayMpec: wire.cost.finder_decay_mpec,
            finderEnhancerDecayMpec: wire.cost.finder_enhancer_decay_mpec ?? 0,
            ampDecayMpec: wire.cost.amp_decay_mpec,
            totalTtMpec: wire.cost.total_tt_mpec,
            totalWithMarkupMpec: wire.cost.total_with_markup_mpec,
        },
        result: "pending",
        resultEventId: null,
        resultObservedTsMs: null,
        hitId: null,
        hitEventId: null,
        resourceName: null,
        sizeLabel: null,
        sizeIndex: null,
        expectedExpiresTsMs: null,
        rangeM: null,
        depthM: null,
    };
}

export function miningDropDtoWithHitHint(
    drop: MiningDropDto,
    wire: MiningHitHintEventWire,
    eventId: number = -1,
): MiningDropDto {
    return {
        ...drop,
        result: "hit",
        resultEventId: eventId,
        resultObservedTsMs: wire.observed_ts_ms,
        hitId: wire.hit_id,
        hitEventId: eventId,
        resourceName: wire.resource_name,
        sizeLabel: wire.size_label,
        sizeIndex: wire.size_index,
        expectedExpiresTsMs: wire.expected_expires_ts_ms ?? null,
        rangeM: wire.range_m,
        depthM: wire.depth_m,
    };
}

export function miningDropDtoWithNoResources(
    drop: MiningDropDto,
    wire: MiningNoResourcesEventWire,
    eventId: number = -1,
): MiningDropDto {
    if (drop.result === "hit") {
        return drop;
    }
    return {
        ...drop,
        result: "no_resources",
        resultEventId: eventId,
        resultObservedTsMs: wire.observed_ts_ms,
    };
}

export function miningDropDtoWithClaimCreated(
    drop: MiningDropDto,
    wire: MiningClaimCreatedEventWire,
    eventId: number = -1,
): MiningDropDto {
    return {
        ...drop,
        result: "hit",
        resultEventId: drop.result === "hit" ? drop.resultEventId : eventId,
        resultObservedTsMs: drop.result === "hit" ? drop.resultObservedTsMs : wire.observed_ts_ms,
        hitId: drop.hitId ?? wire.hit_id,
        resourceName: wire.resource_name ?? drop.resourceName,
        sizeLabel: wire.size_label ?? drop.sizeLabel,
        sizeIndex: wire.size_index ?? drop.sizeIndex,
        expectedExpiresTsMs: wire.expected_expires_ts_ms ?? drop.expectedExpiresTsMs,
        rangeM: wire.range_m ?? drop.rangeM,
        depthM: wire.depth_m ?? drop.depthM,
    };
}

function wireToPositionDto(wire: MiningDropPositionWire): MiningDropPositionDto {
    return {
        planetName: wire.planet_name ?? "",
        x: wire.x,
        y: wire.y,
        z: wire.z ?? null,
    };
}

function isMiningDropCostWire(value: unknown): value is MiningDropCostWire {
    if (!isRecord(value)) return false;
    return (
        isFiniteNumber(value.ammo_cost_mpec) &&
        isFiniteNumber(value.probes_cost_mpec) &&
        isFiniteNumber(value.finder_decay_mpec) &&
        isFiniteNumber(value.finder_enhancer_decay_mpec) &&
        isFiniteNumber(value.amp_decay_mpec) &&
        isFiniteNumber(value.total_tt_mpec) &&
        isFiniteNumber(value.total_with_markup_mpec)
    );
}

function isMiningDropEventCostWire(value: unknown): value is MiningDropEventCostWire {
    if (!isRecord(value)) return false;
    return (
        isCostComponentWire(value.ammo) &&
        isCostComponentWire(value.probes) &&
        isFiniteNumber(value.finder_decay_mpec) &&
        (value.finder_enhancer_decay_mpec === undefined ||
            isFiniteNumber(value.finder_enhancer_decay_mpec)) &&
        isFiniteNumber(value.amp_decay_mpec) &&
        isFiniteNumber(value.total_tt_mpec) &&
        isFiniteNumber(value.total_with_markup_mpec)
    );
}

function isCostComponentWire(value: unknown): value is MiningDropEventCostComponentWire {
    if (!isRecord(value)) return false;
    return isNullableNumber(value.quantity) && isFiniteNumber(value.cost_mpec) && typeof value.source === "string";
}

function isMiningDropResult(value: unknown): value is MiningDropResult {
    return value === "pending" || value === "hit" || value === "no_resources";
}

function isNullablePositionWire(value: unknown): value is MiningDropPositionWire | null {
    return value === null || isPositionWire(value);
}

function isPositionWire(value: unknown): value is MiningDropPositionWire {
    if (!isRecord(value)) return false;
    return (
        isNullableString(value.planet_name) &&
        isFiniteNumber(value.x) &&
        isFiniteNumber(value.y) &&
        (value.z === undefined || isNullableNumber(value.z))
    );
}

function isNullableNumber(value: unknown): value is number | null {
    return value === null || isFiniteNumber(value);
}

function isFiniteNumber(value: unknown): value is number {
    return typeof value === "number" && Number.isFinite(value);
}

function isNullableString(value: unknown): value is string | null {
    return value === null || typeof value === "string";
}

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === "object" && value !== null;
}
