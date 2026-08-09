import type { components } from "@zml/api-contract";

export type MiningToolKind = components["schemas"]["MiningToolProfileDto"]["kind"];

export type MiningToolProfileDto = {
    toolId: string;
    kind: MiningToolKind;
    name: string;
    decayMpec: number;
    markupPercent: string;
    radiusM: number | null;
};

export type ActiveMiningToolsDto = {
    finderId: string | null;
    ampId: string | null;
    extractorId: string | null;
    finderRangeEnhancerCount: number;
    effectiveFinderRadiusM: number | null;
    extractionCostMpec: number | null;
};

export type CreateMiningToolProfileRequest = {
    kind: MiningToolKind;
    name: string;
    decayMpec: number;
    markupPercent: string;
    radiusM: number | null;
};

export type SetActiveMiningToolsRequest = {
    finderId: string | null;
    ampId: string | null;
    extractorId: string | null;
    finderRangeEnhancerCount: number;
};

export type MiningToolProfileWire = components["schemas"]["MiningToolProfileDto"];
export type ActiveMiningToolsWire = components["schemas"]["ActiveMiningToolsDto"];
export type CreateMiningToolProfileRequestWire =
    components["schemas"]["CreateMiningToolProfileRequestDto"];
export type SetActiveMiningToolsRequestWire =
    components["schemas"]["SetActiveMiningToolsRequestDto"];

export function isMiningToolProfileWire(value: unknown): value is MiningToolProfileWire {
    if (!isRecord(value)) return false;
    return (
        typeof value.tool_id === "string" &&
        isMiningToolKind(value.kind) &&
        typeof value.name === "string" &&
        isFiniteNumber(value.decay_mpec) &&
        typeof value.markup_percent === "string" &&
        isNullableNumber(value.radius_m)
    );
}

export function isActiveMiningToolsWire(value: unknown): value is ActiveMiningToolsWire {
    if (!isRecord(value)) return false;
    return (
        isNullableString(value.finder_id) &&
        isNullableString(value.amp_id) &&
        isNullableString(value.extractor_id) &&
        isFiniteNumber(value.finder_range_enhancer_count) &&
        isNullableNumber(value.effective_finder_radius_m) &&
        isNullableNumber(value.extraction_cost_mpec)
    );
}

export function isCreateMiningToolProfileRequest(
    value: unknown,
): value is CreateMiningToolProfileRequest {
    if (!isRecord(value)) return false;
    return (
        isMiningToolKind(value.kind) &&
        typeof value.name === "string" &&
        isFiniteNumber(value.decayMpec) &&
        typeof value.markupPercent === "string" &&
        isNullableNumber(value.radiusM)
    );
}

export function isSetActiveMiningToolsRequest(value: unknown): value is SetActiveMiningToolsRequest {
    if (!isRecord(value)) return false;
    return (
        isNullableString(value.finderId) &&
        isNullableString(value.ampId) &&
        isNullableString(value.extractorId) &&
        isFiniteNumber(value.finderRangeEnhancerCount)
    );
}

export function wireToMiningToolProfileDto(wire: MiningToolProfileWire): MiningToolProfileDto {
    return {
        toolId: wire.tool_id,
        kind: wire.kind,
        name: wire.name,
        decayMpec: wire.decay_mpec,
        markupPercent: wire.markup_percent,
        radiusM: wire.radius_m ?? null,
    };
}

export function wireToActiveMiningToolsDto(wire: ActiveMiningToolsWire): ActiveMiningToolsDto {
    return {
        finderId: wire.finder_id,
        ampId: wire.amp_id,
        extractorId: wire.extractor_id,
        finderRangeEnhancerCount: wire.finder_range_enhancer_count,
        effectiveFinderRadiusM: wire.effective_finder_radius_m,
        extractionCostMpec: wire.extraction_cost_mpec,
    };
}

export function createMiningToolProfileRequestToWire(
    request: CreateMiningToolProfileRequest,
): CreateMiningToolProfileRequestWire {
    return {
        kind: request.kind,
        name: request.name,
        decay_mpec: request.decayMpec,
        markup_percent: request.markupPercent,
        radius_m: request.radiusM,
    };
}

export function setActiveMiningToolsRequestToWire(
    request: SetActiveMiningToolsRequest,
): SetActiveMiningToolsRequestWire {
    return {
        finder_id: request.finderId,
        amp_id: request.ampId,
        extractor_id: request.extractorId,
        finder_range_enhancer_count: request.finderRangeEnhancerCount,
    };
}

export function isMiningToolKind(value: unknown): value is MiningToolKind {
    return value === "finder" || value === "amp" || value === "extractor";
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
