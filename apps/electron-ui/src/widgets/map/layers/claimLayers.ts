import { COORDINATE_SYSTEM } from "@deck.gl/core";
import { ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import type { Color, ClaimResourceKind, MapClaim } from "../mapTypes";

const RESOURCE_COLORS: Record<ClaimResourceKind, Color> = {
  crude_oil: [117, 222, 58, 230],
  lysterium_stone: [226, 226, 226, 230],
  belkar_stone: [119, 205, 235, 230],
};

function formatTimer(currentSec: number, expiresAtSec: number): string {
  const remainingSeconds = Math.max(0, expiresAtSec - currentSec);
  const minutes = Math.floor(remainingSeconds / 60);
  const seconds = remainingSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

export function createClaimPointLayer(claims: readonly MapClaim[]): ScatterplotLayer<MapClaim> | null {
  if (claims.length === 0) return null;

  return new ScatterplotLayer<MapClaim>({
    id: "debug-active-claims",
    data: claims,
    coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
    radiusUnits: "pixels",
    lineWidthUnits: "pixels",
    stroked: true,
    filled: true,
    getPosition: (claim) => claim.position,
    getRadius: () => 4,
    getFillColor: (claim) => RESOURCE_COLORS[claim.resourceKind],
    getLineColor: () => [20, 24, 22, 210],
    getLineWidth: () => 1,
  });
}

export function createClaimTimerLayer(
  claims: readonly MapClaim[],
  currentSec: number,
): TextLayer<MapClaim> | null {
  if (claims.length === 0) return null;

  return new TextLayer<MapClaim>({
    id: "debug-active-claim-timers",
    data: claims,
    coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
    billboard: true,
    characterSet: "0123456789:",
    fontFamily: '"Pixel Operator Mono", Geneva, sans-serif',
    fontWeight: 550,
    getPosition: (claim) => claim.position,
    getText: (claim) => formatTimer(currentSec, claim.expiresAtSec),
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
