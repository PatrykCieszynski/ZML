import { describe, expect, it } from "vitest";

import { buildMapTileUrl } from "./mapTileUrl";

describe("buildMapTileUrl", () => {
  it("uses the Vite public root during development", () => {
    expect(buildMapTileUrl("/", "Maps/Calypso", 2, 4)).toBe(
      "/Maps/Calypso/x2_y4.webp",
    );
  });

  it("keeps assets relative to the packaged renderer document", () => {
    expect(buildMapTileUrl("./", "Maps/Next Island", 0, 1)).toBe(
      "./Maps/Next%20Island/x0_y1.webp",
    );
  });

  it("normalizes slashes around the configured tile folder", () => {
    expect(buildMapTileUrl(".", "/Maps/Calypso/", 8, 0)).toBe(
      "./Maps/Calypso/x8_y0.webp",
    );
  });
});
