import { useEffect, useMemo, useState } from "react";
import DeckGL from "@deck.gl/react";
import {
  OrthographicView,
  type OrthographicViewState,
  type ViewStateChangeParameters,
} from "@deck.gl/core";
import type { MiningDropDto, PlanetId } from "@zml/shared";
import { createClaimPointLayer, createClaimTimerLayer } from "./layers/claimLayers";
import { createMapTileLayer } from "./layers/mapTileLayer";
import { createMiningDropRadiusLayer, createMiningHitTimerLayer } from "./layers/miningDropLayers";
import { createPlayerMarkerLayer, createPlayerRangeLayer } from "./layers/playerLayers";
import { compactLayers } from "./mapLayerUtils";
import {
  createInitialMapViewState,
  entropiaToDeckPosition,
  type EntropiaMapPoint,
} from "./mapProjection";
import { createDebugClaims } from "./mocks/debugClaims";
import type { DeckPoint, MapMiningDrop } from "./mapTypes";

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
const DEFAULT_PLAYER_RADIUS_M = 55;

function nowSec(): number {
  return Math.floor(Date.now() / 1000);
}

export function MapViewport({
  planetId,
  point,
  miningDrops,
}: {
  planetId: PlanetId;
  point: EntropiaMapPoint | null;
  miningDrops: readonly MiningDropDto[];
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

  const mapMiningDrops = useMemo<MapMiningDrop[]>(
    () =>
      miningDrops.flatMap((drop) => {
        if (!drop.position || !isDropOnPlanet(planetId, drop)) return [];

        return [
          {
            id: drop.dropId,
            x: drop.position.x,
            y: drop.position.y,
            position: entropiaToDeckPosition(planetId, drop.position),
            result: drop.result,
            radiusM: drop.dropRadiusM,
            hitExpiresAtSec:
              drop.result === "hit" && drop.expectedExpiresTsMs !== null
                ? Math.floor(drop.expectedExpiresTsMs / 1000)
                : null,
          },
        ];
      }),
    [miningDrops, planetId],
  );
  const playerRangeRadiusM = useMemo(
    () =>
      miningDrops.find((drop) => isDropOnPlanet(planetId, drop))?.dropRadiusM ??
      DEFAULT_PLAYER_RADIUS_M,
    [miningDrops, planetId],
  );
  const hasMiningHitTimers = useMemo(
    () => mapMiningDrops.some((drop) => drop.result === "hit" && drop.hitExpiresAtSec !== null),
    [mapMiningDrops],
  );

  useEffect(() => {
    setViewState(createInitialMapViewState(planetId));
  }, [planetId]);

  useEffect(() => {
    if (!DEBUG_CLAIMS_ENABLED && !hasMiningHitTimers) return;

    const timer = window.setInterval(() => setCurrentSec(nowSec()), 1000);
    return () => window.clearInterval(timer);
  }, [hasMiningHitTimers]);

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
    () => createPlayerRangeLayer(planetId, marker, playerRangeRadiusM),
    [marker, planetId, playerRangeRadiusM],
  );
  const playerMarkerLayer = useMemo(() => createPlayerMarkerLayer(marker), [marker]);
  const miningDropRadiusLayer = useMemo(
    () => createMiningDropRadiusLayer(planetId, mapMiningDrops),
    [mapMiningDrops, planetId],
  );
  const miningHitTimerLayer = useMemo(
    () => createMiningHitTimerLayer(mapMiningDrops, currentSec),
    [currentSec, mapMiningDrops],
  );

  const layers = useMemo(
    () =>
      compactLayers([
        tileLayer,
        miningDropRadiusLayer,
        miningHitTimerLayer,
        debugClaimPointLayer,
        debugClaimTimerLayer,
        playerRangeLayer,
        playerMarkerLayer,
      ]),
    [
      debugClaimPointLayer,
      debugClaimTimerLayer,
      miningHitTimerLayer,
      miningDropRadiusLayer,
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

function isDropOnPlanet(planetId: PlanetId, drop: MiningDropDto): boolean {
  const planetName = drop.position?.planetName;
  if (!planetName) return true;
  return planetName.toLowerCase() === planetId;
}
