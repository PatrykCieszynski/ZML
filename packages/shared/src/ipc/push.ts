import type { OcrPositionEvent } from "../events/envelope";
import type { OcrPositionDTO } from "../dto/ocrPosition";
import type { MiningClaimDto } from "../dto/miningClaims";
import type { MiningDropDto } from "../dto/miningDrops";
import type { ActiveMiningToolsDto, MiningToolProfileDto } from "../dto/miningTools";
import type { RunDto, RunSegmentDto } from "../agent/runs";
import type { BootstrapAgentState, BootstrapStreamsState } from "./bootstrap";

// Main -> Renderer (map/hud) push payload
export type PushPosition = {
    event: OcrPositionEvent;
};

export type RuntimeStatePatch = {
    agent?: BootstrapAgentState;
    streams?: BootstrapStreamsState;
    position?: OcrPositionDTO;
    activeRun?: RunDto | null;
    runSegments?: RunSegmentDto[];
    miningClaims?: MiningClaimDto[];
    miningDrops?: MiningDropDto[];
    miningTools?: MiningToolProfileDto[];
    activeMiningTools?: ActiveMiningToolsDto;
};

export type PushStatePatch = {
    patch: RuntimeStatePatch;
};
