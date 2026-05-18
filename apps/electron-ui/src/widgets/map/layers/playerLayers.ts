import { COORDINATE_SYSTEM } from "@deck.gl/core";
import { ScatterplotLayer } from "@deck.gl/layers";
import type { PlanetId } from "@zml/shared";
import { coordRadiusToDeckRadius } from "../mapProjection";
import type { DeckPoint } from "../mapTypes";

export function createPlayerRangeLayer(planetId: PlanetId, marker: DeckPoint | null): ScatterplotLayer<DeckPoint> | null {
  if (!marker) return null;

  return new ScatterplotLayer<DeckPoint>({
    id: "player-range",
    data: [marker],
    coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
    radiusUnits: "common",
    lineWidthUnits: "pixels",
    stroked: true,
    filled: true,
    getPosition: (item) => item.position,
    getRadius: () => coordRadiusToDeckRadius(planetId, 110),
    getFillColor: () => [80, 190, 110, 28],
    getLineColor: () => [145, 255, 170, 170],
    getLineWidth: () => 2,
  });
}

export function createPlayerMarkerLayer(marker: DeckPoint | null): ScatterplotLayer<DeckPoint> | null {
  if (!marker) return null;

  return new ScatterplotLayer<DeckPoint>({
    id: "player-marker",
    data: [marker],
    coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
    radiusUnits: "pixels",
    lineWidthUnits: "pixels",
    stroked: true,
    filled: true,
    getPosition: (item) => item.position,
    getRadius: () => 6,
    getFillColor: () => [246, 248, 255, 255],
    getLineColor: () => [36, 235, 113, 255],
    getLineWidth: () => 2,
  });
}

