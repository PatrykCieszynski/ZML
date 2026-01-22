import type { WorldPosDTO } from "./worldPos.ts";

export type OcrPositionDTO = {
    tsMs: number;
    position: WorldPosDTO;
};
