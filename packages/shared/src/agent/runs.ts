export type RunDto = {
    runId: number;
    name: string;
    status: string;
    notes?: string | null;
    createdTsMs?: number;
    updatedTsMs?: number;
};

export type RunWire = {
    run_id: number;
    name: string;
    status: string;
    notes?: string | null;
    created_ts_ms?: number;
    updated_ts_ms?: number;
};

export type RunSegmentDto = {
    segmentId: string;
    runId: number;
    segmentIndex: number;
    status: string;
    startedTsMs: number;
    endedTsMs: number | null;
    setupHash: string;
    setupSnapshot: Record<string, unknown>;
    notes: string | null;
    createdTsMs: number;
    updatedTsMs: number;
};

export type RunSegmentWire = {
    segment_id: string;
    run_id: number;
    segment_index: number;
    status: string;
    started_ts_ms: number;
    ended_ts_ms: number | null;
    setup_hash: string;
    setup_snapshot: Record<string, unknown>;
    notes?: string | null;
    created_ts_ms: number;
    updated_ts_ms: number;
};

export type RunSegmentStartedEventWire = {
    segment_id: string;
    run_id: number;
    segment_index: number;
    started_ts_ms: number;
    setup_hash: string;
    setup_snapshot: Record<string, unknown>;
};

export type RunSegmentEndedEventWire = {
    segment_id: string;
    run_id: number;
    ended_ts_ms: number;
    reason: string;
};

export type StartRunRequest = {
    name: string;
    notes?: string | null;
};

export type StopRunRequest = {
    runId?: number;
};

export function isStartRunRequest(value: unknown): value is StartRunRequest {
    if (!isRecord(value)) return false;
    const record = value;
    return typeof record.name === "string" && record.name.trim().length > 0;
}

export function isStopRunRequest(value: unknown): value is StopRunRequest {
    if (!isRecord(value)) return false;
    return value.runId === undefined || isFiniteNumber(value.runId);
}

export function isRunWire(value: unknown): value is RunWire {
    if (!isRecord(value)) return false;
    return (
        isFiniteNumber(value.run_id) &&
        typeof value.name === "string" &&
        typeof value.status === "string" &&
        (value.notes === undefined || isNullableString(value.notes)) &&
        (value.created_ts_ms === undefined || isFiniteNumber(value.created_ts_ms)) &&
        (value.updated_ts_ms === undefined || isFiniteNumber(value.updated_ts_ms))
    );
}

export function isRunWireOrNull(value: unknown): value is RunWire | null {
    return value === null || isRunWire(value);
}

export function isRunSegmentWire(value: unknown): value is RunSegmentWire {
    if (!isRecord(value)) return false;
    return (
        typeof value.segment_id === "string" &&
        isFiniteNumber(value.run_id) &&
        isFiniteNumber(value.segment_index) &&
        typeof value.status === "string" &&
        isFiniteNumber(value.started_ts_ms) &&
        isNullableNumber(value.ended_ts_ms) &&
        typeof value.setup_hash === "string" &&
        isRecord(value.setup_snapshot) &&
        (value.notes === undefined || isNullableString(value.notes)) &&
        isFiniteNumber(value.created_ts_ms) &&
        isFiniteNumber(value.updated_ts_ms)
    );
}

export function isRunSegmentStartedEventWire(value: unknown): value is RunSegmentStartedEventWire {
    if (!isRecord(value)) return false;
    return (
        typeof value.segment_id === "string" &&
        isFiniteNumber(value.run_id) &&
        isFiniteNumber(value.segment_index) &&
        isFiniteNumber(value.started_ts_ms) &&
        typeof value.setup_hash === "string" &&
        isRecord(value.setup_snapshot)
    );
}

export function isRunSegmentEndedEventWire(value: unknown): value is RunSegmentEndedEventWire {
    if (!isRecord(value)) return false;
    return (
        typeof value.segment_id === "string" &&
        isFiniteNumber(value.run_id) &&
        isFiniteNumber(value.ended_ts_ms) &&
        typeof value.reason === "string"
    );
}

export function wireToRunDto(wire: RunWire): RunDto {
    return {
        runId: wire.run_id,
        name: wire.name,
        status: wire.status,
        notes: wire.notes ?? null,
        createdTsMs: wire.created_ts_ms,
        updatedTsMs: wire.updated_ts_ms,
    };
}

export function wireToRunSegmentDto(wire: RunSegmentWire): RunSegmentDto {
    return {
        segmentId: wire.segment_id,
        runId: wire.run_id,
        segmentIndex: wire.segment_index,
        status: wire.status,
        startedTsMs: wire.started_ts_ms,
        endedTsMs: wire.ended_ts_ms,
        setupHash: wire.setup_hash,
        setupSnapshot: wire.setup_snapshot,
        notes: wire.notes ?? null,
        createdTsMs: wire.created_ts_ms,
        updatedTsMs: wire.updated_ts_ms,
    };
}

export function runSegmentDtoFromStartedEventWire(
    wire: RunSegmentStartedEventWire,
    createdTsMs: number,
): RunSegmentDto {
    return {
        segmentId: wire.segment_id,
        runId: wire.run_id,
        segmentIndex: wire.segment_index,
        status: "active",
        startedTsMs: wire.started_ts_ms,
        endedTsMs: null,
        setupHash: wire.setup_hash,
        setupSnapshot: wire.setup_snapshot,
        notes: null,
        createdTsMs,
        updatedTsMs: createdTsMs,
    };
}

export function runSegmentDtoWithEndedEvent(
    segment: RunSegmentDto,
    wire: RunSegmentEndedEventWire,
    updatedTsMs: number,
): RunSegmentDto {
    return {
        ...segment,
        status: "ended",
        endedTsMs: wire.ended_ts_ms,
        updatedTsMs,
    };
}

export function startRunRequestToWire(request: StartRunRequest): StartRunRequest {
    return {
        name: request.name.trim(),
        notes: request.notes ?? null,
    };
}

export function stopRunRequestToWire(request: StopRunRequest): { run_id?: number } {
    return {
        run_id: request.runId,
    };
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
