import type { OcrPositionEvent } from "../events/envelope";
import type { OcrPositionDTO } from "../dto/ocrPosition";
import type { MiningClaimDto } from "../dto/miningClaims";
import type { MiningDropDto } from "../dto/miningDrops";
import type { MiningLootItemDto, MiningLootTotalDto } from "../dto/miningLoot";
import type { ActiveMiningToolsDto, MiningToolProfileDto } from "../dto/miningTools";
import type { RunDto, RunSegmentDto } from "../backend/runs";
import type { CloudConnectionState } from "../cloud/cloudConnection";
import type { BootstrapAgentState, BootstrapStreamsState } from "./bootstrap";

// Main -> Renderer (map/hud) push payload
export type PushPosition = {
    event: OcrPositionEvent;
};

export type RuntimeStatePatch = {
    agent?: BootstrapAgentState;
    streams?: BootstrapStreamsState;
    cloud?: CloudConnectionState;
    position?: OcrPositionDTO;
    mapWindowVisible?: boolean;
    overlayWindowVisible?: boolean;
    activeRun?: RunDto | null;
    runs?: RunDto[];
    runSegments?: RunSegmentDto[];
    miningClaims?: MiningClaimDto[];
    miningDrops?: MiningDropDto[];
    miningLoot?: MiningLootItemDto[];
    miningLootTotals?: MiningLootTotalDto[];
    miningTools?: MiningToolProfileDto[];
    activeMiningTools?: ActiveMiningToolsDto;
};

export type PushStatePatch = {
    patch: RuntimeStatePatch;
};
