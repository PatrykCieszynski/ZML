import {
  MAP_CONFIG,
  coordRadiusToPixel,
  getMapSizePx,
  worldToPixel,
  type PlanetId,
} from "@zml/shared";
import type { OrthographicViewState } from "@deck.gl/core";

export type EntropiaMapPoint = { x: number; y: number };
export type DeckPosition = [number, number, number];

export function createInitialMapViewState(planetId: PlanetId): OrthographicViewState {
  const { width, height } = getMapSizePx(MAP_CONFIG, planetId);
  return {
    target: [width / 2, height / 2, 0],
    zoom: -0.6,
    minZoom: -2.5,
    maxZoom: 6,
  };
}

export function entropiaToDeckPosition(planetId: PlanetId, point: EntropiaMapPoint): DeckPosition {
  const pixel = worldToPixel(MAP_CONFIG, planetId, point.x, point.y);
  return [pixel.px, pixel.py, 0];
}

export function coordRadiusToDeckRadius(planetId: PlanetId, radiusCoord: number): number {
  return coordRadiusToPixel(MAP_CONFIG, planetId, radiusCoord);
}

