import { COORDINATE_SYSTEM } from "@deck.gl/core";
import { ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import type { PlanetId } from "@desktop/shared";
import { coordRadiusToDeckRadius } from "../mapProjection";
import type { Color, MapMiningDrop } from "../mapTypes";

const DROP_RADIUS_LINE_COLORS: Record<MapMiningDrop["result"], Color> = {
  pending: [255, 221, 78, 210],
  hit: [76, 224, 131, 220],
  no_resources: [175, 185, 198, 135],
};

const DROP_RADIUS_FILL_COLORS: Record<MapMiningDrop["result"], Color> = {
  pending: [255, 221, 78, 22],
  hit: [76, 224, 131, 28],
  no_resources: [175, 185, 198, 12],
};

function formatHitTimer(currentSec: number, expiresAtSec: number): string {
  const remainingSeconds = Math.max(0, expiresAtSec - currentSec);
  const hours = Math.floor(remainingSeconds / 3600);
  const minutes = Math.floor((remainingSeconds % 3600) / 60);
  const seconds = remainingSeconds % 60;
  if (hours > 0) {
    return `${hours}:${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
  }
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

export function createMiningDropRadiusLayer(
  planetId: PlanetId,
  drops: readonly MapMiningDrop[],
): ScatterplotLayer<MapMiningDrop> | null {
  if (drops.length === 0) return null;

  return new ScatterplotLayer<MapMiningDrop>({
    id: "mining-drop-radii",
    data: drops,
    coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
    radiusUnits: "common",
    lineWidthUnits: "pixels",
    stroked: true,
    filled: true,
    getPosition: (drop) => drop.position,
    getRadius: (drop) => coordRadiusToDeckRadius(planetId, drop.radiusM),
    getFillColor: (drop) => DROP_RADIUS_FILL_COLORS[drop.result],
    getLineColor: (drop) => DROP_RADIUS_LINE_COLORS[drop.result],
    getLineWidth: (drop) => (drop.result === "pending" ? 2 : 1),
  });
}

export function createMiningHitTimerLayer(
  drops: readonly MapMiningDrop[],
  currentSec: number,
): TextLayer<MapMiningDrop> | null {
  const hitDrops = drops.filter((drop) => drop.result === "hit" && drop.hitExpiresAtSec !== null);
  if (hitDrops.length === 0) return null;

  return new TextLayer<MapMiningDrop>({
    id: "mining-hit-timers",
    data: hitDrops,
    coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
    billboard: true,
    characterSet: "0123456789:",
    fontFamily: '"Pixel Operator Mono", Geneva, sans-serif',
    fontWeight: 550,
    getPosition: (drop) => drop.position,
    getText: (drop) => formatHitTimer(currentSec, drop.hitExpiresAtSec ?? currentSec),
    getSize: () => 12,
    getColor: () => [255, 242, 82, 255],
    getPixelOffset: () => [0, 12],
    getTextAnchor: () => "middle",
    getAlignmentBaseline: () => "center",
    fontSettings: {
      sdf: true,
      fontSize: 18,
      buffer: 1,
    },
  });
}
