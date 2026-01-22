import type { WorldPosDTO } from "./worldPos";

export type OcrPositionDTO = {
    tsMs: number;
    position: WorldPosDTO;
};

export type OcrPositionWire = {
    ts_ms: number;
    planet_name: string;
    x: number;
    y: number;
    z: number | null;
};

export function wireToOcrPositionDTO(w: OcrPositionWire): OcrPositionDTO {
    return {
        tsMs: w.ts_ms,
        position: {
            planetName: w.planet_name ?? "",
            x: w.x,
            y: w.y,
            z: w.z ?? null,
        },
    };
}