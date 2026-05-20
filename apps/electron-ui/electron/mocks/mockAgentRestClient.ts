import type { AgentHealthDto, MiningDropDto, RunDto, StartRunRequest, StopRunRequest } from "@zml/shared";

import type { AgentClient, ListMiningDropsRequest } from "../agent/restClient.ts";

const MOCK_MINING_DROPS: MiningDropDto[] = [
    createMockMiningDrop("mock-drop-1", Date.now() - 9 * 60_000, 58890, 84639, "no_resources"),
    createMockMiningDrop("mock-drop-2", Date.now() - 5 * 60_000, 58913, 84653, "hit"),
    createMockMiningDrop("mock-drop-3", Date.now() - 90_000, 58940, 84667, "pending"),
];

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

    async listMiningDrops(request: ListMiningDropsRequest = {}): Promise<MiningDropDto[]> {
        const windowMs = (request.windowMinutes ?? 30) * 60_000;
        const cutoff = Date.now() - windowMs;
        return MOCK_MINING_DROPS.filter((drop) => drop.observedTsMs >= cutoff);
    }
}

function createMockMiningDrop(
    dropId: string,
    observedTsMs: number,
    x: number,
    y: number,
    result: MiningDropDto["result"],
): MiningDropDto {
    const isHit = result === "hit";
    const isFinished = result !== "pending";

    return {
        dropId,
        dropEventId: -1,
        observedTsMs,
        position: {
            planetName: "Calypso",
            x,
            y,
            z: null,
        },
        dropRadiusM: result === "hit" ? 55.2 : 55,
        modesMask: 1,
        probesPerDrop: null,
        ammoPerDrop: 1000,
        cost: {
            ammoCostMpec: 10000,
            probesCostMpec: 0,
            finderDecayMpec: 0,
            ampDecayMpec: 0,
            totalMpec: 10000,
        },
        result,
        resultEventId: isFinished ? -1 : null,
        resultObservedTsMs: isFinished ? observedTsMs + 1500 : null,
        hitId: isHit ? `${dropId}-hit` : null,
        hitEventId: isHit ? -1 : null,
        resourceName: isHit ? "Lysterium Stone" : null,
        sizeLabel: isHit ? "Minimal" : null,
        sizeIndex: isHit ? 1 : null,
        rangeM: isHit ? 51.14 : null,
        depthM: isHit ? 53 : null,
    };
}
