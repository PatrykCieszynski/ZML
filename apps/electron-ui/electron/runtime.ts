import type {
    BootstrapAgentState,
    BootstrapStreamsState,
    MiningDropDto,
    OcrPositionDTO,
} from "@zml/shared";

export type RuntimeState = {
    seq: number;
    agent: BootstrapAgentState;
    streams: BootstrapStreamsState;
    lastError?: string | null;
    lastPosition?: OcrPositionDTO;
    miningDrops: MiningDropDto[];
};

export const runtime: RuntimeState = {
    seq: 0,
    agent: { status: "connecting" },
    streams: { ws: false, sse: false },
    lastPosition: undefined,
    miningDrops: [],
};
