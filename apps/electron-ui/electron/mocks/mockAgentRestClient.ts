import type { AgentHealthDto, RunDto, StartRunRequest, StopRunRequest } from "@zml/shared";

import type { AgentClient } from "../agent/restClient.ts";

export class MockAgentRestClient implements AgentClient {
    private nextRunId = 1;
    private activeRun: RunDto | null = null;

    async getHealth(): Promise<AgentHealthDto> {
        return { status: "mock" };
    }

    async startRun(request: StartRunRequest): Promise<RunDto> {
        const now = Date.now();
        this.activeRun = {
            runId: this.nextRunId,
            name: request.name.trim(),
            status: "running",
            notes: request.notes ?? null,
            createdTsMs: now,
            updatedTsMs: now,
        };
        this.nextRunId += 1;

        return this.activeRun;
    }

    async stopRun(request: StopRunRequest): Promise<RunDto> {
        const now = Date.now();
        const run = this.activeRun ?? {
            runId: request.runId ?? 0,
            name: "Mock run",
            status: "running",
            notes: null,
            createdTsMs: now,
        };

        const stoppedRun: RunDto = {
            ...run,
            status: "stopped",
            updatedTsMs: now,
        };

        this.activeRun = null;

        return stoppedRun;
    }
}
