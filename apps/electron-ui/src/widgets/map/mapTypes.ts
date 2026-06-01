import type { DeckPosition, EntropiaMapPoint } from "./mapProjection";

export type Color = [number, number, number, number];

export type DeckPoint = {
  position: DeckPosition;
};

export type MiningType = "ore" | "enmatter" | "treasure";
export type ClaimResourceKind = "crude_oil" | "lysterium_stone" | "belkar_stone" | "unknown";

export type MapClaim = EntropiaMapPoint & {
  id: string;
  position: DeckPosition;
  resourceKind: ClaimResourceKind;
  resourceName: string | null;
  sizeLabel: string | null;
  sizeIndex: number | null;
  expiresAtSec: number | null;
};

export type MapMiningDrop = EntropiaMapPoint & {
  id: string;
  position: DeckPosition;
  result: "pending" | "hit" | "no_resources";
  radiusM: number;
  hitExpiresAtSec: number | null;
};
