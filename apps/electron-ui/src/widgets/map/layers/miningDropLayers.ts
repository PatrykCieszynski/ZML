import { COORDINATE_SYSTEM } from "@deck.gl/core";
import { ScatterplotLayer } from "@deck.gl/layers";
import type { PlanetId } from "@zml/shared";
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
