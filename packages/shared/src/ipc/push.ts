import type { OcrPositionEvent } from "../events/envelope";

// Main -> Renderer (map/hud) push payload
export type PushPosition = {
    event: OcrPositionEvent;
};
