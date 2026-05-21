import { useEffect, useMemo, useState } from "react";
import DeckGL from "@deck.gl/react";
import {
  OrthographicView,
  type OrthographicViewState,
  type ViewStateChangeParameters,
} from "@deck.gl/core";
import type { MiningClaimDto, MiningDropDto, PlanetId } from "@zml/shared";
import { createClaimPointLayer, createClaimTimerLayer } from "./layers/claimLayers";
import { createMapTileLayer } from "./layers/mapTileLayer";
import { createMiningDropRadiusLayer } from "./layers/miningDropLayers";
import { createPlayerMarkerLayer, createPlayerRangeLayer } from "./layers/playerLayers";
import { compactLayers } from "./mapLayerUtils";
import {
  createInitialMapViewState,
  entropiaToDeckPosition,
  type EntropiaMapPoint,
} from "./mapProjection";
import { createDebugClaims } from "./mocks/debugClaims";
import type { ClaimResourceKind, DeckPoint, MapClaim, MapMiningDrop } from "./mapTypes";

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
  miningClaims,
  miningDrops,
}: {
  planetId: PlanetId;
  point: EntropiaMapPoint | null;
  miningClaims: readonly MiningClaimDto[];
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
  const mapMiningClaims = useMemo<MapClaim[]>(
    () =>
      miningClaims.flatMap((claim) => {
        if (claim.status !== "active" || !claim.position || !isClaimOnPlanet(planetId, claim)) {
          return [];
        }

        return [
          {
            id: claim.claimId,
            x: claim.position.x,
            y: claim.position.y,
            position: entropiaToDeckPosition(planetId, claim.position),
            resourceKind: resourceKindFromName(claim.resourceName),
            expiresAtSec:
              claim.expectedExpiresTsMs !== null
                ? Math.floor(claim.expectedExpiresTsMs / 1000)
                : null,
          },
        ];
      }),
    [miningClaims, planetId],
  );
  const hasClaimTimers = useMemo(
    () => mapMiningClaims.some((claim) => claim.expiresAtSec !== null),
    [mapMiningClaims],
  );

  useEffect(() => {
    setViewState(createInitialMapViewState(planetId));
  }, [planetId]);

  useEffect(() => {
    if (!DEBUG_CLAIMS_ENABLED && !hasClaimTimers) return;

    const timer = window.setInterval(() => setCurrentSec(nowSec()), 1000);
    return () => window.clearInterval(timer);
  }, [hasClaimTimers]);

  const tileLayer = useMemo(() => createMapTileLayer(planetId), [planetId]);
  const debugClaims = useMemo(
    () =>
      DEBUG_CLAIMS_ENABLED
        ? createDebugClaims(planetId, debugClaimSeedSec)
        : [],
    [debugClaimSeedSec, planetId],
  );

  const activeClaims = useMemo(
    () => (DEBUG_CLAIMS_ENABLED ? [...mapMiningClaims, ...debugClaims] : mapMiningClaims),
    [debugClaims, mapMiningClaims],
  );
  const claimPointLayer = useMemo(() => createClaimPointLayer(activeClaims), [activeClaims]);
  const claimTimerLayer = useMemo(
    () => createClaimTimerLayer(activeClaims, currentSec),
    [activeClaims, currentSec],
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
  const layers = useMemo(
    () =>
      compactLayers([
        tileLayer,
        miningDropRadiusLayer,
        claimPointLayer,
        claimTimerLayer,
        playerRangeLayer,
        playerMarkerLayer,
      ]),
    [
      claimPointLayer,
      claimTimerLayer,
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

function isClaimOnPlanet(planetId: PlanetId, claim: MiningClaimDto): boolean {
  const planetName = claim.position?.planetName;
  if (!planetName) return true;
  return planetName.toLowerCase() === planetId;
}

function resourceKindFromName(resourceName: string | null): ClaimResourceKind {
  const normalized = resourceName?.trim().toLowerCase();
  if (normalized === "crude oil") return "crude_oil";
  if (normalized === "lysterium stone") return "lysterium_stone";
  if (normalized === "belkar stone") return "belkar_stone";
  return "unknown";
}
