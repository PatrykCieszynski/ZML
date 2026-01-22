import type { AgentStatus, OcrPositionDTO } from "@zml/shared";

export type RuntimeState = {
    seq: number;
    agent: { status: AgentStatus };
    streams: { ws: boolean; sse: boolean };
    lastPosition?: OcrPositionDTO;
};

export const runtime: RuntimeState = {
    seq: 0,
    agent: { status: "connecting" },
    streams: { ws: false, sse: false },
    lastPosition: undefined,
};
