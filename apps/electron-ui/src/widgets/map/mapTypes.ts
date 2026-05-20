import type { DeckPosition, EntropiaMapPoint } from "./mapProjection";

export type Color = [number, number, number, number];

export type DeckPoint = {
  position: DeckPosition;
};

export type MiningType = "ore" | "enmatter" | "treasure";
export type ClaimResourceKind = "crude_oil" | "lysterium_stone" | "belkar_stone";

export type MapClaim = EntropiaMapPoint & {
  id: string;
  position: DeckPosition;
  miningType: MiningType;
  resourceKind: ClaimResourceKind;
  expiresAtSec: number;
};

export type MapMiningDrop = EntropiaMapPoint & {
  id: string;
  position: DeckPosition;
  result: "pending" | "hit" | "no_resources";
  radiusM: number;
  hitExpiresAtSec: number | null;
};
