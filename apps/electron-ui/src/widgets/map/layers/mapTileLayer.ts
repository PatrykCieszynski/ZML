import { COORDINATE_SYSTEM } from "@deck.gl/core";
import { TileLayer, type NonGeoBoundingBox } from "@deck.gl/geo-layers";
import { BitmapLayer } from "@deck.gl/layers";
import {
  MAP_CONFIG,
  getMapSizePx,
  type PlanetId,
  type PlanetMapConfig,
} from "@zml/shared";

function getAvailableTileKeys(planet: PlanetMapConfig): Set<string> {
  if (planet.availableTiles) {
    return new Set(planet.availableTiles.map(([x, y]) => `${x}:${y}`));
  }

  const keys = new Set<string>();
  for (let y = 0; y < planet.tileCountY; y++) {
    for (let x = 0; x < planet.tileCountX; x++) {
      keys.add(`${x}:${y}`);
    }
  }
  return keys;
}

function isNonGeoBoundingBox(bbox: unknown): bbox is NonGeoBoundingBox {
  return (
    typeof bbox === "object" &&
    bbox !== null &&
    "left" in bbox &&
    "top" in bbox &&
    "right" in bbox &&
    "bottom" in bbox
  );
}

export function createMapTileLayer(planetId: PlanetId): TileLayer<string | null> {
  const planet = MAP_CONFIG.planets[planetId];
  const { width, height } = getMapSizePx(MAP_CONFIG, planetId);
  const availableTileKeys = getAvailableTileKeys(planet);
  const base = encodeURI(
    planet.tileFolder.startsWith("/")
      ? planet.tileFolder
      : `/${planet.tileFolder}`,
  );

  return new TileLayer<string | null>({
    id: `${planetId}-map-tiles`,
    data: null,
    tileSize: planet.tileSize,
    minZoom: 0,
    maxZoom: 0,
    extent: [0, 0, width, height],
    maxCacheSize: planet.tileCountX * planet.tileCountY,
    refinementStrategy: "no-overlap",
    getTileData: ({ index }) => {
      if (
        index.z !== 0 ||
        index.x < 0 ||
        index.y < 0 ||
        index.x >= planet.tileCountX ||
        index.y >= planet.tileCountY ||
        !availableTileKeys.has(`${index.x}:${index.y}`)
      ) {
        return null;
      }

      return `${base}/x${index.x}_y${index.y}.webp`;
    },
    onTileError: () => undefined,
    renderSubLayers: ({ data, tile }) => {
      if (!data || !isNonGeoBoundingBox(tile.bbox)) return null;

      return new BitmapLayer({
        id: `${tile.id}-bitmap`,
        image: data,
        // BitmapLayer expects [left, bottom, right, top]. The TileLayer bbox is
        // top-left based, which matches the map pixel space used by flipY=true.
        bounds: [tile.bbox.left, tile.bbox.bottom, tile.bbox.right, tile.bbox.top],
        pickable: false,
        coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
      });
    },
  });
}

