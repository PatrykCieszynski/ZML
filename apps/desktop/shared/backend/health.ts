import type { components } from "@zml/api-contract";

export type WorkerHealthState = components["schemas"]["WorkerHealthDto"]["state"];

export type WorkerHealthDto = {
    state: WorkerHealthState;
    enabled: boolean;
    lastError: string | null;
    lastSeenTsMs: number;
};

export type BackendHealthDto = {
    status: WorkerHealthState;
    workers: Record<string, WorkerHealthDto>;
};

export type WorkerHealthWire = components["schemas"]["WorkerHealthDto"];
export type BackendHealthWire = components["schemas"]["HealthDto"];

export function isBackendHealthWire(value: unknown): value is BackendHealthWire {
    if (!isRecord(value) || !isWorkerHealthState(value.status) || !isRecord(value.workers)) {
        return false;
    }
    return Object.values(value.workers).every(isWorkerHealthWire);
}

export function wireToBackendHealthDto(wire: BackendHealthWire): BackendHealthDto {
    return {
        status: wire.status,
        workers: Object.fromEntries(
            Object.entries(wire.workers).map(([name, worker]) => [
                name,
                {
                    state: worker.state,
                    enabled: worker.enabled,
                    lastError: worker.last_error,
                    lastSeenTsMs: worker.last_seen_ts_ms,
                },
            ]),
        ),
    };
}

function isWorkerHealthWire(value: unknown): value is WorkerHealthWire {
    if (!isRecord(value)) return false;
    return (
        isWorkerHealthState(value.state) &&
        typeof value.enabled === "boolean" &&
        (value.last_error === null || typeof value.last_error === "string") &&
        typeof value.last_seen_ts_ms === "number" &&
        Number.isFinite(value.last_seen_ts_ms)
    );
}

function isWorkerHealthState(value: unknown): value is WorkerHealthState {
    return (
        value === "running" ||
        value === "degraded" ||
        value === "crashed" ||
        value === "stopped"
    );
}

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === "object" && value !== null;
}
