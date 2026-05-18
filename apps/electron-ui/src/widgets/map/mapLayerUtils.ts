import type { Layer, LayersList } from "@deck.gl/core";

export function compactLayers(layers: Array<Layer | null>): LayersList {
  return layers.filter((layer): layer is Layer => layer !== null);
}

