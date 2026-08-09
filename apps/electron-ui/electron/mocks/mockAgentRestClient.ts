import type {
    ActiveMiningToolsDto,
    AgentHealthDto,
    CreateMiningToolProfileRequest,
    MiningClaimDto,
    MiningDropDto,
    MiningLootItemDto,
    MiningLootTotalDto,
    MiningToolKind,
    MiningToolProfileDto,
    RunDto,
    RunSegmentDto,
    SetActiveMiningToolsRequest,
    StartRunRequest,
    StopRunRequest,
    UpdateRunRequest,
} from "@desktop/shared";

import type {
    AgentClient,
    ListMiningClaimsRequest,
    ListMiningDropsRequest,
    ListMiningLootRequest,
    ListMiningLootTotalsRequest,
} from "../agent/restClient.ts";

const MOCK_MINING_CLAIMS: MiningClaimDto[] = [
    createMockMiningClaim("mock-claim-1", Date.now() - 5 * 60_000, 58913, 84653, "Lysterium Stone", "ore"),
    createMockMiningClaim("mock-claim-2", Date.now() - 90_000, 58940, 84667, "Crude Oil", "enmatter"),
    createMockMiningClaim("mock-claim-3", Date.now() - 18 * 60_000, 58890, 84639, "Belkar Stone", "ore", "depleted"),
];

const MOCK_MINING_DROPS: MiningDropDto[] = [
    createMockMiningDrop("mock-drop-1", Date.now() - 9 * 60_000, 58890, 84639, "no_resources"),
    createMockMiningDrop("mock-drop-2", Date.now() - 5 * 60_000, 58913, 84653, "hit"),
    createMockMiningDrop("mock-drop-3", Date.now() - 90_000, 58940, 84667, "pending"),
];

const MOCK_MINING_LOOT: MiningLootItemDto[] = [
    createMockMiningLoot(1, Date.now() - 4 * 60_000, "Lysterium Stone", 8, 64_000, 170),
    createMockMiningLoot(2, Date.now() - 3 * 60_000, "Lysterium Stone", 4, 32_000, 170),
    createMockMiningLoot(3, Date.now() - 2 * 60_000, "Crude Oil", 12, 120_000, 170),
];

export class MockAgentRestClient implements AgentClient {
    private nextRunId = 1;
    private nextToolId = 4;
    private activeRun: RunDto | null = null;
    private runs: RunDto[] = [];
    private runSegments: RunSegmentDto[] = [];
    private miningClaims: MiningClaimDto[] = [...MOCK_MINING_CLAIMS];
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
        const now = Date.now();
        return {
            status: "running",
            workers: {
                db_writer: {
                    state: "running",
                    enabled: true,
                    lastError: null,
                    lastSeenTsMs: now,
                },
                input_coordinator: {
                    state: "running",
                    enabled: true,
                    lastError: null,
                    lastSeenTsMs: now,
                },
                ocr_worker: {
                    state: "running",
                    enabled: true,
                    lastError: null,
                    lastSeenTsMs: now,
                },
                chat_tail: {
                    state: "running",
                    enabled: true,
                    lastError: null,
                    lastSeenTsMs: now,
                },
            },
        };
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
        this.runs = [this.activeRun, ...this.runs.filter((run) => run.runId !== this.activeRun?.runId)];
        this.runSegments = [];

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
        this.runs = [stoppedRun, ...this.runs.filter((item) => item.runId !== stoppedRun.runId)];
        this.runSegments = [];

        return stoppedRun;
    }

    async getActiveRun(): Promise<RunDto | null> {
        return this.activeRun;
    }

    async listRuns(): Promise<RunDto[]> {
        return this.runs.filter((run) => run.status !== "deleted");
    }

    async resumeRun(runId: number): Promise<RunDto> {
        const current = this.runs.find((run) => run.runId === runId);
        if (current?.status === "deleted") {
            throw new Error(`Mock run not found: ${runId}`);
        }

        const now = Date.now();
        this.activeRun = {
            runId,
            name: current?.name ?? `Mock run #${runId}`,
            status: "running",
            notes: current?.notes ?? null,
            createdTsMs: current?.createdTsMs ?? now,
            updatedTsMs: now,
        };
        this.runs = [this.activeRun, ...this.runs.filter((run) => run.runId !== runId)];
        this.runSegments = [];
        return this.activeRun;
    }

    async updateRun(runId: number, request: UpdateRunRequest): Promise<RunDto> {
        const current = this.runs.find((run) => run.runId === runId);
        if (!current || current.status === "deleted") {
            throw new Error(`Mock run not found: ${runId}`);
        }

        const updatedRun: RunDto = {
            ...current,
            name: request.name?.trim() || current.name,
            notes: request.notes === undefined ? current.notes : request.notes,
            updatedTsMs: Date.now(),
        };

        this.runs = [updatedRun, ...this.runs.filter((run) => run.runId !== runId)];
        if (this.activeRun?.runId === runId) {
            this.activeRun = updatedRun;
        }
        return updatedRun;
    }

    async deleteRun(runId: number): Promise<RunDto> {
        const current = this.runs.find((run) => run.runId === runId);
        if (!current) {
            throw new Error(`Mock run not found: ${runId}`);
        }

        const deletedRun: RunDto = {
            ...current,
            status: "deleted",
            updatedTsMs: Date.now(),
        };

        this.runs = [deletedRun, ...this.runs.filter((run) => run.runId !== runId)];
        if (this.activeRun?.runId === runId) {
            this.activeRun = null;
            this.runSegments = [];
        }
        return deletedRun;
    }

    async listActiveRunSegments(): Promise<RunSegmentDto[]> {
        return this.activeRun === null ? [] : [...this.runSegments];
    }

    async listRunSegments(runId: number): Promise<RunSegmentDto[]> {
        if (this.activeRun?.runId !== runId) return [];
        return [...this.runSegments];
    }

    async listMiningClaims(request: ListMiningClaimsRequest = {}): Promise<MiningClaimDto[]> {
        if (request.activeRun && this.activeRun === null) return [];
        const runId = request.activeRun ? this.activeRun?.runId ?? null : request.runId ?? null;
        const claims = runId === null
            ? this.miningClaims
            : this.miningClaims.filter((claim) => claim.runId === runId);
        if (request.active === false) return claims;
        return claims.filter((claim) => claim.status === "active");
    }

    async ignoreMiningClaim(
        claimId: string,
    ): Promise<MiningClaimDto> {
        const current = this.miningClaims.find((claim) => claim.claimId === claimId);
        if (!current) {
            throw new Error(`Mock claim not found: ${claimId}`);
        }
        const updated: MiningClaimDto = { ...current, status: "ignored" };
        this.miningClaims = [updated, ...this.miningClaims.filter((claim) => claim.claimId !== claimId)];
        return updated;
    }

    async markMiningClaimDepleted(
        claimId: string,
    ): Promise<MiningClaimDto> {
        const current = this.miningClaims.find((claim) => claim.claimId === claimId);
        if (!current) {
            throw new Error(`Mock claim not found: ${claimId}`);
        }
        const updated: MiningClaimDto = {
            ...current,
            status: "depleted",
            depletedEventDt: new Date().toISOString(),
            depletedPosition: current.position,
            depletedDistanceM: 0,
        };
        this.miningClaims = [updated, ...this.miningClaims.filter((claim) => claim.claimId !== claimId)];
        return updated;
    }

    async listMiningDrops(request: ListMiningDropsRequest = {}): Promise<MiningDropDto[]> {
        if (request.activeRun || request.runId !== undefined || request.windowMinutes === undefined) {
            return [...MOCK_MINING_DROPS];
        }

        const windowMs = request.windowMinutes * 60_000;
        const cutoff = Date.now() - windowMs;
        return MOCK_MINING_DROPS.filter((drop) => drop.observedTsMs >= cutoff);
    }

    async listMiningLoot(request: ListMiningLootRequest = {}): Promise<MiningLootItemDto[]> {
        if (request.activeRun && this.activeRun === null) return [];
        const runId = request.activeRun ? this.activeRun?.runId ?? null : request.runId ?? null;
        if (runId === null) return [...MOCK_MINING_LOOT];
        return MOCK_MINING_LOOT.filter((item) => item.runId === runId);
    }

    async listMiningLootTotals(
        request: ListMiningLootTotalsRequest = {},
    ): Promise<MiningLootTotalDto[]> {
        const loot = await this.listMiningLoot({
            runId: request.runId,
            activeRun: request.activeRun,
        });
        return buildMockLootTotals(loot);
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
            runId: null,
            segmentId: null,
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
            totalTtMpec: 10000,
            totalWithMarkupMpec: 10000,
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

function createMockMiningLoot(
    eventId: number,
    createdTsMs: number,
    itemName: string,
    qty: number,
    valueMpec: number,
    extractionCostMpec: number | null,
): MiningLootItemDto {
    return {
        eventId,
        createdTsMs,
        eventDt: new Date(createdTsMs).toISOString(),
        runId: 1,
        segmentId: null,
        itemName,
        qty,
        valueMpec,
        extractionCostMpec,
    };
}

function buildMockLootTotals(loot: MiningLootItemDto[]): MiningLootTotalDto[] {
    const rows = new Map<string, MiningLootTotalDto>();
    for (const item of loot) {
        const current = rows.get(item.itemName);
        rows.set(item.itemName, {
            scope: "run",
            runId: item.runId ?? 1,
            segmentId: null,
            itemName: item.itemName,
            qty: (current?.qty ?? 0) + item.qty,
            valueMpec: (current?.valueMpec ?? 0) + item.valueMpec,
            extractionCostMpec: (current?.extractionCostMpec ?? 0) + (item.extractionCostMpec ?? 0),
            eventCount: (current?.eventCount ?? 0) + 1,
            firstSeenTsMs: Math.min(current?.firstSeenTsMs ?? item.createdTsMs, item.createdTsMs),
            lastSeenTsMs: Math.max(current?.lastSeenTsMs ?? item.createdTsMs, item.createdTsMs),
        });
    }
    return [...rows.values()].sort((a, b) => b.valueMpec - a.valueMpec);
}

function createMockMiningClaim(
    claimId: string,
    observedTsMs: number,
    x: number,
    y: number,
    resourceName: string,
    miningType: MiningClaimDto["miningType"],
    status: MiningClaimDto["status"] = "active",
): MiningClaimDto {
    return {
        claimId,
        createdEventId: -1,
        hitId: `${claimId}-hit`,
        dropId: `${claimId}-drop`,
        runId: 1,
        segmentId: "mock-segment-1",
        observedTsMs,
        position: {
            planetName: "Calypso",
            x,
            y,
            z: null,
        },
        searchRadiusM: 55,
        resourceName,
        miningType,
        sizeLabel: "Minimal",
        sizeIndex: 1,
        expectedExpiresTsMs: observedTsMs + 60 * 60_000,
        rangeM: 51.14,
        depthM: 53,
        status,
        depletedEventId: status === "depleted" ? -2 : null,
        depletedEventDt: status === "depleted" ? new Date(observedTsMs + 8 * 60_000).toISOString() : null,
        depletedPosition: status === "depleted"
            ? {
                planetName: "Calypso",
                x: x + 4,
                y: y + 3,
                z: null,
            }
            : null,
        depletedDistanceM: status === "depleted" ? 5 : null,
    };
}
