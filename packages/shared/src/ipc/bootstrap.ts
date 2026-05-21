import type { WindowType } from "./windowType";
import type { OcrPositionDTO } from "../dto/ocrPosition";
import type { MiningClaimDto } from "../dto/miningClaims";
import type { MiningDropDto } from "../dto/miningDrops";
import type { ActiveMiningToolsDto, MiningToolProfileDto } from "../dto/miningTools";
import type { RunDto, RunSegmentDto } from "../agent/runs";

export const IPC_VERSION = 1 as const;
export type IpcVersion = typeof IPC_VERSION;

export type AgentStatus = "connecting" | "connected" | "disconnected";

export type BootstrapAgentState = {
    status: AgentStatus;
    lastError?: string | null;
};

export type BootstrapStreamsState = {
    ws: boolean;
    sse: boolean;
};

export type GetBootstrapStateReq = {
    windowType: WindowType;
};

export type BootstrapState = {
    ipcVersion: IpcVersion;
    windowType: WindowType;

    nowTsMs: number;

    agent: BootstrapAgentState;
    streams: BootstrapStreamsState;

    // Last known position (if any)
    position?: OcrPositionDTO;
    activeRun?: RunDto | null;
    runSegments?: RunSegmentDto[];
    miningClaims?: MiningClaimDto[];
    miningDrops?: MiningDropDto[];
    miningTools?: MiningToolProfileDto[];
    activeMiningTools?: ActiveMiningToolsDto;
};
