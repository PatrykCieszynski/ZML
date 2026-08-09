export type EventType =
    | "ocr.position";

export type EventEnvelope<TType extends string, TPayload> = {
    type: TType;
    seq: number;
    tsMs: number;
    payload: TPayload;
};

import type { OcrPositionDTO } from "../dto/ocrPosition";

export type OcrPositionEvent = EventEnvelope<"ocr.position", OcrPositionDTO>;
