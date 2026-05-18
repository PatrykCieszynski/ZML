import type { OcrPositionEvent } from "@zml/shared";

export type PositionSourceStatus = "connecting" | "connected" | "disconnected";

export type PositionSourceOptions = {
    onStatus: (status: PositionSourceStatus, err?: string) => void;
    onEvent: (event: OcrPositionEvent) => void;
};

export type StopPositionSource = () => void;
