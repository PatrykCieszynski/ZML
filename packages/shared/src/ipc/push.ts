import type { OcrPositionEvent } from "../events/envelope";
import type { OcrPositionDTO } from "../dto/ocrPosition";
import type { MiningDropDto } from "../dto/miningDrops";
import type { BootstrapAgentState, BootstrapStreamsState } from "./bootstrap";

// Main -> Renderer (map/hud) push payload
export type PushPosition = {
    event: OcrPositionEvent;
};

export type RuntimeStatePatch = {
    agent?: BootstrapAgentState;
    streams?: BootstrapStreamsState;
    position?: OcrPositionDTO;
    miningDrops?: MiningDropDto[];
};

export type PushStatePatch = {
    patch: RuntimeStatePatch;
};
