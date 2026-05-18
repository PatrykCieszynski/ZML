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

export type StartRunRequest = {
    name: string;
    notes?: string | null;
};

export type StopRunRequest = {
    runId?: number;
};

export function isStartRunRequest(value: unknown): value is StartRunRequest {
    if (typeof value !== "object" || value === null) return false;
    const record = value as Record<string, unknown>;
    return typeof record.name === "string" && record.name.trim().length > 0;
}

export function isStopRunRequest(value: unknown): value is StopRunRequest {
    if (typeof value !== "object" || value === null) return false;
    const record = value as Record<string, unknown>;
    return record.runId === undefined || (typeof record.runId === "number" && Number.isFinite(record.runId));
}

export function isRunWire(value: unknown): value is RunWire {
    if (typeof value !== "object" || value === null) return false;
    const record = value as Record<string, unknown>;
    return (
        typeof record.run_id === "number" &&
        Number.isFinite(record.run_id) &&
        typeof record.name === "string" &&
        typeof record.status === "string"
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
