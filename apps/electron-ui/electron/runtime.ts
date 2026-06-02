import type {
    BootstrapAgentState,
    BootstrapStreamsState,
    ActiveMiningToolsDto,
    MiningClaimDto,
    MiningDropDto,
    MiningLootItemDto,
    MiningLootTotalDto,
    MiningToolProfileDto,
    OcrPositionDTO,
    RunDto,
    RunSegmentDto,
} from "@zml/shared";

export type RuntimeState = {
    seq: number;
    agent: BootstrapAgentState;
    streams: BootstrapStreamsState;
    lastError?: string | null;
    lastPosition?: OcrPositionDTO;
    mapWindowVisible: boolean;
    overlayWindowVisible: boolean;
    activeRun: RunDto | null;
    runs: RunDto[];
    runSegments: RunSegmentDto[];
    miningClaims: MiningClaimDto[];
    miningDrops: MiningDropDto[];
    miningLoot: MiningLootItemDto[];
    miningLootTotals: MiningLootTotalDto[];
    miningTools: MiningToolProfileDto[];
    activeMiningTools?: ActiveMiningToolsDto;
};

export const runtime: RuntimeState = {
    seq: 0,
    agent: { status: "connecting" },
    streams: { ws: false, sse: false },
    lastPosition: undefined,
    mapWindowVisible: false,
    overlayWindowVisible: false,
    activeRun: null,
    runs: [],
    runSegments: [],
    miningClaims: [],
    miningDrops: [],
    miningLoot: [],
    miningLootTotals: [],
    miningTools: [],
    activeMiningTools: undefined,
};
