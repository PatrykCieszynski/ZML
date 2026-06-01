import { MAP_CONFIG, type PlanetId } from "@zml/shared";
import { entropiaToDeckPosition } from "../mapProjection";
import type { ClaimResourceKind, MapClaim } from "../mapTypes";

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

export function createDebugClaims(planetId: PlanetId, seedSec: number): MapClaim[] {
  const planet = MAP_CONFIG.planets[planetId];
  const centerX = (planet.minLon + planet.maxLon) / 2;
  const centerY = (planet.minLat + planet.maxLat) / 2;
  const resources: ClaimResourceKind[] = ["crude_oil", "lysterium_stone", "belkar_stone"];

  return Array.from({ length: 320 }, (_, index) => {
    const ring = 1 + (index % 8);
    const angle = index * 2.399963 + Math.sin(index * 0.37) * 0.45;
    const radius = 55 + ring * 42 + (index % 5) * 9;
    const x = Math.round(clamp(centerX + Math.cos(angle) * radius, planet.minLon, planet.maxLon));
    const y = Math.round(clamp(centerY + Math.sin(angle) * radius * 0.78, planet.minLat, planet.maxLat));

    return {
      id: `debug-claim-${index}`,
      x,
      y,
      position: entropiaToDeckPosition(planetId, { x, y }),
      resourceKind: resources[index % resources.length],
      resourceName: resources[index % resources.length].split("_").join(" "),
      sizeLabel: "Debug",
      sizeIndex: (index % 5) + 1,
      expiresAtSec: seedSec + 90 + index * 11,
    };
  });
}
