import type { MapConfig, PlanetId } from "./mapConfig";

export type PixelPoint = { px: number; py: number };

export function getMapSizePx(cfg: MapConfig, planetId: PlanetId) {
    const p = cfg.planets[planetId];
    return {
        width: p.tileCountX * p.tileSize,
        height: p.tileCountY * p.tileSize,
    };
}

export function worldToPixel(cfg: MapConfig, planetId: PlanetId, lon: number, lat: number): PixelPoint {
    const p = cfg.planets[planetId];
    const { width, height } = getMapSizePx(cfg, planetId);

    const lonRange = p.maxLon - p.minLon;
    const latRange = p.maxLat - p.minLat;
    if (lonRange <= 0 || latRange <= 0) return { px: 0, py: 0 };

    const x = ((lon - p.minLon) / lonRange) * width;

    // IMPORTANT: Y inverted (top-left origin)
    const y = height - ((lat - p.minLat) / latRange) * height;

    return { px: x, py: y };
}

export function coordRadiusToPixel(cfg: MapConfig, planetId: PlanetId, radiusCoord: number): number {
    const p = cfg.planets[planetId];
    const { width } = getMapSizePx(cfg, planetId);
    const lonRange = p.maxLon - p.minLon;
    if (lonRange <= 0) return 0;
    return (radiusCoord / lonRange) * width;
}
