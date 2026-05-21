import type {
    ActiveMiningToolsDto,
    AgentHealthDto,
    CreateMiningToolProfileRequest,
    MiningClaimDto,
    MiningDropDto,
    MiningToolKind,
    MiningToolProfileDto,
    RunDto,
    SetActiveMiningToolsRequest,
    StartRunRequest,
    StopRunRequest,
} from "@zml/shared";

import type {
    AgentClient,
    ListMiningClaimsRequest,
    ListMiningDropsRequest,
} from "../agent/restClient.ts";

const MOCK_MINING_CLAIMS: MiningClaimDto[] = [
    createMockMiningClaim("mock-claim-1", Date.now() - 5 * 60_000, 58913, 84653, "Lysterium Stone"),
    createMockMiningClaim("mock-claim-2", Date.now() - 90_000, 58940, 84667, "Crude Oil"),
];

const MOCK_MINING_DROPS: MiningDropDto[] = [
    createMockMiningDrop("mock-drop-1", Date.now() - 9 * 60_000, 58890, 84639, "no_resources"),
    createMockMiningDrop("mock-drop-2", Date.now() - 5 * 60_000, 58913, 84653, "hit"),
    createMockMiningDrop("mock-drop-3", Date.now() - 90_000, 58940, 84667, "pending"),
];

export class MockAgentRestClient implements AgentClient {
    private nextRunId = 1;
    private nextToolId = 4;
    private activeRun: RunDto | null = null;
    private miningTools: MiningToolProfileDto[] = [
        createMockMiningTool("mock-finder-1", "finder", "Ziplex Z20", 0, "100", 55),
        createMockMiningTool("mock-amp-1", "amp", "Level 2 Amp", 4200, "108", null),
        createMockMiningTool("mock-extractor-1", "extractor", "Genesis Star Excavator", 170, "100", null),
    ];
    private activeMiningTools: ActiveMiningToolsDto = {
        finderId: "mock-finder-1",
        ampId: null,
        extractorId: "mock-extractor-1",
        finderRangeEnhancerCount: 0,
        effectiveFinderRadiusM: 55,
        extractionCostMpec: 170,
    };

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

    async listMiningClaims(request: ListMiningClaimsRequest = {}): Promise<MiningClaimDto[]> {
        if (request.active === false) return MOCK_MINING_CLAIMS;
        return MOCK_MINING_CLAIMS.filter((claim) => claim.status === "active");
    }

    async listMiningDrops(request: ListMiningDropsRequest = {}): Promise<MiningDropDto[]> {
        const windowMs = (request.windowMinutes ?? 30) * 60_000;
        const cutoff = Date.now() - windowMs;
        return MOCK_MINING_DROPS.filter((drop) => drop.observedTsMs >= cutoff);
    }

    async listMiningTools(): Promise<MiningToolProfileDto[]> {
        return [...this.miningTools];
    }

    async createMiningTool(request: CreateMiningToolProfileRequest): Promise<MiningToolProfileDto> {
        const profile: MiningToolProfileDto = {
            toolId: `mock-tool-${this.nextToolId}`,
            kind: request.kind,
            name: request.name.trim(),
            decayMpec: request.decayMpec,
            markupPercent: request.markupPercent,
            radiusM: request.radiusM,
        };
        this.nextToolId += 1;
        this.miningTools = [...this.miningTools, profile];
        return profile;
    }

    async deleteMiningTool(toolId: string): Promise<void> {
        this.miningTools = this.miningTools.filter((profile) => profile.toolId !== toolId);
        if (this.activeMiningTools.finderId === toolId) {
            this.activeMiningTools = {
                ...this.activeMiningTools,
                finderId: null,
                finderRangeEnhancerCount: 0,
                effectiveFinderRadiusM: null,
            };
        }
        if (this.activeMiningTools.ampId === toolId) {
            this.activeMiningTools = { ...this.activeMiningTools, ampId: null };
        }
        if (this.activeMiningTools.extractorId === toolId) {
            this.activeMiningTools = {
                ...this.activeMiningTools,
                extractorId: null,
                extractionCostMpec: null,
            };
        }
    }

    async getActiveMiningTools(): Promise<ActiveMiningToolsDto> {
        return this.activeMiningTools;
    }

    async setActiveMiningTools(request: SetActiveMiningToolsRequest): Promise<ActiveMiningToolsDto> {
        const finder = this.miningTools.find((profile) => profile.toolId === request.finderId);
        const extractor = this.miningTools.find((profile) => profile.toolId === request.extractorId);
        this.activeMiningTools = {
            finderId: request.finderId,
            ampId: request.ampId,
            extractorId: request.extractorId,
            finderRangeEnhancerCount: request.finderRangeEnhancerCount,
            effectiveFinderRadiusM:
                finder?.radiusM === null || finder === undefined
                    ? null
                    : finder.radiusM * (1 + request.finderRangeEnhancerCount * 0.01),
            extractionCostMpec: extractor?.decayMpec ?? null,
        };
        return this.activeMiningTools;
    }
}

function createMockMiningTool(
    toolId: string,
    kind: MiningToolKind,
    name: string,
    decayMpec: number,
    markupPercent: string,
    radiusM: number | null,
): MiningToolProfileDto {
    return {
        toolId,
        kind,
        name,
        decayMpec,
        markupPercent,
        radiusM,
    };
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
            finderEnhancerDecayMpec: 0,
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
        expectedExpiresTsMs: isHit ? observedTsMs + 60 * 60_000 : null,
        rangeM: isHit ? 51.14 : null,
        depthM: isHit ? 53 : null,
    };
}

function createMockMiningClaim(
    claimId: string,
    observedTsMs: number,
    x: number,
    y: number,
    resourceName: string,
): MiningClaimDto {
    return {
        claimId,
        createdEventId: -1,
        hitId: `${claimId}-hit`,
        dropId: `${claimId}-drop`,
        observedTsMs,
        position: {
            planetName: "Calypso",
            x,
            y,
            z: null,
        },
        searchRadiusM: 55,
        resourceName,
        sizeLabel: "Minimal",
        sizeIndex: 1,
        expectedExpiresTsMs: observedTsMs + 60 * 60_000,
        rangeM: 51.14,
        depthM: 53,
        status: "active",
        depletedEventId: null,
        depletedEventDt: null,
        depletedPosition: null,
        depletedDistanceM: null,
    };
}
