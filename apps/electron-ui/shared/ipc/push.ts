import type { OcrPositionEvent } from "../events/envelope.ts";

// Main -> Renderer (map/hud) push payload
export type PushPosition = {
    event: OcrPositionEvent;
};
