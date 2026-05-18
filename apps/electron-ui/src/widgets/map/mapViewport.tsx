import { useEffect, useMemo, useState } from "react";
import DeckGL from "@deck.gl/react";
import {
  OrthographicView,
  type OrthographicViewState,
  type ViewStateChangeParameters,
} from "@deck.gl/core";
import type { PlanetId } from "@zml/shared";
import { createClaimPointLayer, createClaimTimerLayer } from "./layers/claimLayers";
import { createMapTileLayer } from "./layers/mapTileLayer";
import { createPlayerMarkerLayer, createPlayerRangeLayer } from "./layers/playerLayers";
import { compactLayers } from "./mapLayerUtils";
import {
  createInitialMapViewState,
  entropiaToDeckPosition,
  type EntropiaMapPoint,
} from "./mapProjection";
import { createDebugClaims } from "./mocks/debugClaims";
import type { DeckPoint } from "./mapTypes";

const MAP_VIEW = new OrthographicView({
  id: "map",
  flipY: true,
  controller: {
    dragRotate: false,
    doubleClickZoom: false,
    scrollZoom: { speed: 0.01, smooth: true },
  },
});

const DEBUG_CLAIMS_ENABLED = import.meta.env.VITE_ZML_UI_MOCKS === "1";

function nowSec(): number {
  return Math.floor(Date.now() / 1000);
}

export function MapViewport({
  planetId,
  point,
}: {
  planetId: PlanetId;
  point: EntropiaMapPoint | null;
}) {
  const [viewState, setViewState] = useState<OrthographicViewState>(() =>
    createInitialMapViewState(planetId),
  );
  const [currentSec, setCurrentSec] = useState(nowSec);
  const [debugClaimSeedSec] = useState(nowSec);

  const marker = useMemo<DeckPoint | null>(() => {
    if (!point) return null;
    return { position: entropiaToDeckPosition(planetId, point) };
  }, [planetId, point]);

  useEffect(() => {
    setViewState(createInitialMapViewState(planetId));
  }, [planetId]);

  useEffect(() => {
    if (!DEBUG_CLAIMS_ENABLED) return;

    const timer = window.setInterval(() => setCurrentSec(nowSec()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const tileLayer = useMemo(() => createMapTileLayer(planetId), [planetId]);
  const debugClaims = useMemo(
    () =>
      DEBUG_CLAIMS_ENABLED
        ? createDebugClaims(planetId, debugClaimSeedSec)
        : [],
    [debugClaimSeedSec, planetId],
  );

  const debugClaimPointLayer = useMemo(() => createClaimPointLayer(debugClaims), [debugClaims]);
  const debugClaimTimerLayer = useMemo(
    () => createClaimTimerLayer(debugClaims, currentSec),
    [currentSec, debugClaims],
  );
  const playerRangeLayer = useMemo(
    () => createPlayerRangeLayer(planetId, marker),
    [marker, planetId],
  );
  const playerMarkerLayer = useMemo(() => createPlayerMarkerLayer(marker), [marker]);

  const layers = useMemo(
    () =>
      compactLayers([
        tileLayer,
        debugClaimPointLayer,
        debugClaimTimerLayer,
        playerRangeLayer,
        playerMarkerLayer,
      ]),
    [
      debugClaimPointLayer,
      debugClaimTimerLayer,
      playerMarkerLayer,
      playerRangeLayer,
      tileLayer,
    ],
  );

  const handleViewStateChange = ({
    viewState: nextViewState,
  }: ViewStateChangeParameters<OrthographicViewState>) => {
    setViewState({
      ...nextViewState,
      minZoom: -2.5,
      maxZoom: 6,
    });
  };

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        background: "#0b0b0b",
        overflow: "hidden",
        position: "relative",
      }}
    >
      <DeckGL
        views={MAP_VIEW}
        viewState={viewState}
        layers={layers}
        onViewStateChange={handleViewStateChange}
        style={{ position: "absolute", inset: "0" }}
      />
    </div>
  );
}
