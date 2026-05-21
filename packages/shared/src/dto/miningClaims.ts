import type { WorldPosDTO } from "./worldPos";

export type MiningClaimStatus = "active" | "depleted";

export type MiningClaimPositionDto = WorldPosDTO;

export type MiningClaimDto = {
    claimId: string;
    createdEventId: number;
    hitId: string | null;
    dropId: string | null;
    observedTsMs: number;
    position: MiningClaimPositionDto | null;
    searchRadiusM: number | null;
    resourceName: string | null;
    sizeLabel: string | null;
    sizeIndex: number | null;
    expectedExpiresTsMs: number | null;
    rangeM: number | null;
    depthM: number | null;
    status: MiningClaimStatus;
    depletedEventId: number | null;
    depletedEventDt: string | null;
    depletedPosition: MiningClaimPositionDto | null;
    depletedDistanceM: number | null;
};

export type MiningClaimPositionWire = {
    planet_name: string | null;
    x: number;
    y: number;
    z?: number | null;
};

export type MiningClaimWire = {
    claim_id: string;
    created_event_id: number;
    hit_id: string | null;
    drop_id: string | null;
    observed_ts_ms: number;
    position: MiningClaimPositionWire | null;
    search_radius_m: number | null;
    resource_name: string | null;
    size_label: string | null;
    size_index: number | null;
    expected_expires_ts_ms: number | null;
    range_m: number | null;
    depth_m: number | null;
    status: MiningClaimStatus;
    depleted_event_id: number | null;
    depleted_event_dt: string | null;
    depleted_position: MiningClaimPositionWire | null;
    depleted_distance_m: number | null;
};

export type MiningClaimCreatedEventWire = {
    claim_id: string;
    hit_id: string | null;
    drop_id: string | null;
    observed_ts_ms: number;
    position: MiningClaimPositionWire | null;
    search_radius_m: number | null;
    resource_name: string | null;
    size_label: string | null;
    size_index: number | null;
    expected_expires_ts_ms: number | null;
    range_m: number | null;
    depth_m: number | null;
};

export type MiningClaimDepletedEventWire = {
    claim_id: string;
    drop_id: string | null;
    hit_id: string | null;
    position: MiningClaimPositionWire;
    distance_m: number;
};

export function isMiningClaimWire(value: unknown): value is MiningClaimWire {
    if (!isRecord(value)) return false;
    return (
        typeof value.claim_id === "string" &&
        isFiniteNumber(value.created_event_id) &&
        isNullableString(value.hit_id) &&
        isNullableString(value.drop_id) &&
        isFiniteNumber(value.observed_ts_ms) &&
        isNullablePositionWire(value.position) &&
        isNullableNumber(value.search_radius_m) &&
        isNullableString(value.resource_name) &&
        isNullableString(value.size_label) &&
        isNullableNumber(value.size_index) &&
        isNullableNumber(value.expected_expires_ts_ms) &&
        isNullableNumber(value.range_m) &&
        isNullableNumber(value.depth_m) &&
        isMiningClaimStatus(value.status) &&
        isNullableNumber(value.depleted_event_id) &&
        isNullableString(value.depleted_event_dt) &&
        isNullablePositionWire(value.depleted_position) &&
        isNullableNumber(value.depleted_distance_m)
    );
}

export function isMiningClaimCreatedEventWire(
    value: unknown,
): value is MiningClaimCreatedEventWire {
    if (!isRecord(value)) return false;
    return (
        typeof value.claim_id === "string" &&
        isNullableString(value.hit_id) &&
        isNullableString(value.drop_id) &&
        isFiniteNumber(value.observed_ts_ms) &&
        isNullablePositionWire(value.position) &&
        isNullableNumber(value.search_radius_m) &&
        isNullableString(value.resource_name) &&
        isNullableString(value.size_label) &&
        isNullableNumber(value.size_index) &&
        isNullableNumber(value.expected_expires_ts_ms) &&
        isNullableNumber(value.range_m) &&
        isNullableNumber(value.depth_m)
    );
}

export function isMiningClaimDepletedEventWire(
    value: unknown,
): value is MiningClaimDepletedEventWire {
    if (!isRecord(value)) return false;
    return (
        typeof value.claim_id === "string" &&
        isNullableString(value.drop_id) &&
        isNullableString(value.hit_id) &&
        isPositionWire(value.position) &&
        isFiniteNumber(value.distance_m)
    );
}

export function wireToMiningClaimDto(wire: MiningClaimWire): MiningClaimDto {
    return {
        claimId: wire.claim_id,
        createdEventId: wire.created_event_id,
        hitId: wire.hit_id,
        dropId: wire.drop_id,
        observedTsMs: wire.observed_ts_ms,
        position: wire.position ? wireToPositionDto(wire.position) : null,
        searchRadiusM: wire.search_radius_m,
        resourceName: wire.resource_name,
        sizeLabel: wire.size_label,
        sizeIndex: wire.size_index,
        expectedExpiresTsMs: wire.expected_expires_ts_ms,
        rangeM: wire.range_m,
        depthM: wire.depth_m,
        status: wire.status,
        depletedEventId: wire.depleted_event_id,
        depletedEventDt: wire.depleted_event_dt,
        depletedPosition: wire.depleted_position ? wireToPositionDto(wire.depleted_position) : null,
        depletedDistanceM: wire.depleted_distance_m,
    };
}

export function miningClaimDtoFromCreatedEventWire(
    wire: MiningClaimCreatedEventWire,
    eventId: number = -1,
): MiningClaimDto {
    return {
        claimId: wire.claim_id,
        createdEventId: eventId,
        hitId: wire.hit_id,
        dropId: wire.drop_id,
        observedTsMs: wire.observed_ts_ms,
        position: wire.position ? wireToPositionDto(wire.position) : null,
        searchRadiusM: wire.search_radius_m,
        resourceName: wire.resource_name,
        sizeLabel: wire.size_label,
        sizeIndex: wire.size_index,
        expectedExpiresTsMs: wire.expected_expires_ts_ms,
        rangeM: wire.range_m,
        depthM: wire.depth_m,
        status: "active",
        depletedEventId: null,
        depletedEventDt: null,
        depletedPosition: null,
        depletedDistanceM: null,
    };
}

function wireToPositionDto(wire: MiningClaimPositionWire): MiningClaimPositionDto {
    return {
        planetName: wire.planet_name ?? "",
        x: wire.x,
        y: wire.y,
        z: wire.z ?? null,
    };
}

function isMiningClaimStatus(value: unknown): value is MiningClaimStatus {
    return value === "active" || value === "depleted";
}

function isNullablePositionWire(value: unknown): value is MiningClaimPositionWire | null {
    return value === null || isPositionWire(value);
}

function isPositionWire(value: unknown): value is MiningClaimPositionWire {
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
