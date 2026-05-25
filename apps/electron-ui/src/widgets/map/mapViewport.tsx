import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
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
    scrollZoom: false,
  },
});
const MAP_VIEWS = [MAP_VIEW];

const DEBUG_CLAIMS_ENABLED = import.meta.env.VITE_ZML_UI_MOCKS === "1";
const DEFAULT_PLAYER_RADIUS_M = 55;
const MAP_MIN_ZOOM = -2.5;
const MAP_MAX_ZOOM = 6;
const MAP_WHEEL_ZOOM_SPEED = 0.0016;
const MAP_WHEEL_ZOOM_EASE = 0.22;
const MAP_WHEEL_ZOOM_SETTLE_THRESHOLD = 0.003;

function nowSec(): number {
  return Math.floor(Date.now() / 1000);
}

export function MapViewport({
  planetId,
  point,
  miningClaims,
  miningDrops,
  playerRadiusM,
  followPlayer,
  onFollowPlayerChange,
}: {
  planetId: PlanetId;
  point: EntropiaMapPoint | null;
  miningClaims: readonly MiningClaimDto[];
  miningDrops: readonly MiningDropDto[];
  playerRadiusM?: number | null;
  followPlayer: boolean;
  onFollowPlayerChange: (followPlayer: boolean) => void;
}) {
  const [viewState, setViewState] = useState<OrthographicViewState>(() =>
    createInitialMapViewState(planetId),
  );
  const mapRootRef = useRef<HTMLDivElement | null>(null);
  const viewStateRef = useRef(viewState);
  const targetZoomRef = useRef(readZoom(viewState.zoom));
  const zoomAnimationFrameIdRef = useRef<number | null>(null);
  const followPlayerRef = useRef(followPlayer);
  const markerRef = useRef<DeckPoint | null>(null);
  const [currentSec, setCurrentSec] = useState(nowSec);
  const [debugClaimSeedSec] = useState(nowSec);

  useEffect(() => {
    viewStateRef.current = viewState;
    if (zoomAnimationFrameIdRef.current === null) {
      targetZoomRef.current = readZoom(viewState.zoom);
    }
  }, [viewState]);

  const marker = useMemo<DeckPoint | null>(() => {
    if (!point) return null;
    return { position: entropiaToDeckPosition(planetId, point) };
  }, [planetId, point]);

  useEffect(() => {
    followPlayerRef.current = followPlayer;
  }, [followPlayer]);

  useEffect(() => {
    markerRef.current = marker;
  }, [marker]);

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
      playerRadiusM ??
      miningDrops.find((drop) => isDropOnPlanet(planetId, drop))?.dropRadiusM ??
      DEFAULT_PLAYER_RADIUS_M,
    [miningDrops, planetId, playerRadiusM],
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
    const initialViewState = createInitialMapViewState(planetId);
    targetZoomRef.current = readZoom(initialViewState.zoom);
    setViewState(initialViewState);
  }, [planetId]);

  const runZoomTick = useCallback(function runZoomTick() {
    zoomAnimationFrameIdRef.current = null;

    const current = viewStateRef.current;
    const currentZoom = readZoom(current.zoom);
    const targetZoom = targetZoomRef.current;
    const zoomDelta = targetZoom - currentZoom;
    const nextZoom =
      Math.abs(zoomDelta) <= MAP_WHEEL_ZOOM_SETTLE_THRESHOLD
        ? targetZoom
        : currentZoom + zoomDelta * MAP_WHEEL_ZOOM_EASE;
    const markerSnapshot = markerRef.current;
    const nextTarget =
      followPlayerRef.current && markerSnapshot !== null
        ? markerSnapshot.position
        : current.target;

    setViewState({
      ...current,
      zoom: nextZoom,
      zoomX: nextZoom,
      zoomY: nextZoom,
      target: nextTarget,
      minZoom: MAP_MIN_ZOOM,
      maxZoom: MAP_MAX_ZOOM,
    });

    if (Math.abs(targetZoom - nextZoom) <= MAP_WHEEL_ZOOM_SETTLE_THRESHOLD) {
      return;
    }

    zoomAnimationFrameIdRef.current = window.requestAnimationFrame(runZoomTick);
  }, []);

  const restartZoomAnimation = useCallback(() => {
    if (zoomAnimationFrameIdRef.current !== null) {
      window.cancelAnimationFrame(zoomAnimationFrameIdRef.current);
      zoomAnimationFrameIdRef.current = null;
    }
    runZoomTick();
  }, [runZoomTick]);

  useEffect(() => {
    const handleWheel = (event: WheelEvent) => {
      const element = mapRootRef.current;

      if (element === null) {
        return;
      }

      const insideElement = isWheelInsideElement(event, element);
      if (!insideElement) {
        return;
      }

      event.preventDefault();
      event.stopPropagation();
      const deltaY = normalizeWheelDeltaY(event);

      if (deltaY === 0) {
        return;
      }

      if (zoomAnimationFrameIdRef.current === null) {
        targetZoomRef.current = readZoom(viewStateRef.current.zoom);
      }
      targetZoomRef.current = clamp(
        targetZoomRef.current - deltaY * MAP_WHEEL_ZOOM_SPEED,
        MAP_MIN_ZOOM,
        MAP_MAX_ZOOM,
      );
      restartZoomAnimation();
    };

    window.addEventListener("wheel", handleWheel, { capture: true, passive: false });
    return () => {
      window.removeEventListener("wheel", handleWheel, { capture: true });
    };
  }, [restartZoomAnimation]);

  useEffect(() => {
    return () => {
      if (zoomAnimationFrameIdRef.current !== null) {
        window.cancelAnimationFrame(zoomAnimationFrameIdRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (!followPlayer || marker === null) return;
    setViewState((current) => ({
      ...current,
      target: marker.position,
      minZoom: MAP_MIN_ZOOM,
      maxZoom: MAP_MAX_ZOOM,
    }));
  }, [followPlayer, marker]);

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
  const deckViewState = useMemo(() => ({ map: viewState }), [viewState]);

  const handleViewStateChange = ({
    viewState: nextViewState,
    interactionState,
  }: ViewStateChangeParameters<OrthographicViewState>) => {
    const current = viewStateRef.current;
    const nextZoom = readZoom(nextViewState.zoom);
    const currentZoom = readZoom(current.zoom);
    const zoomChanged = Math.abs(nextZoom - currentZoom) > 0.0001;
    const shouldDetachFollow =
      followPlayer &&
      !zoomChanged &&
      hasUserMapInteraction(interactionState);
    if (shouldDetachFollow) {
      onFollowPlayerChange(false);
    }
    setViewState({
      ...nextViewState,
      zoom: nextZoom,
      zoomX: nextZoom,
      zoomY: nextZoom,
      target:
        zoomChanged
          ? current.target
          : followPlayer && !shouldDetachFollow && marker !== null
            ? marker.position
            : nextViewState.target,
      minZoom: MAP_MIN_ZOOM,
      maxZoom: MAP_MAX_ZOOM,
    });
  };

  return (
    <div
      ref={mapRootRef}
      style={{
        width: "100%",
        height: "100%",
        background: "#0b0b0b",
        overflow: "hidden",
        position: "relative",
      }}
    >
      <DeckGL
        views={MAP_VIEWS}
        viewState={deckViewState}
        layers={layers}
        onViewStateChange={handleViewStateChange}
        style={{ position: "absolute", inset: "0" }}
      />
    </div>
  );
}

function hasUserMapInteraction(
  interactionState: ViewStateChangeParameters<OrthographicViewState>["interactionState"],
): boolean {
  return Boolean(
    interactionState?.isDragging ||
      interactionState?.isPanning,
  );
}

function readZoom(value: OrthographicViewState["zoom"]): number {
  if (Array.isArray(value)) return value[0] ?? 0;
  return typeof value === "number" ? value : 0;
}

function normalizeWheelDeltaY(event: WheelEvent): number {
  if (event.deltaMode === WheelEvent.DOM_DELTA_LINE) return event.deltaY * 16;
  if (event.deltaMode === WheelEvent.DOM_DELTA_PAGE) return event.deltaY * window.innerHeight;
  return event.deltaY;
}

function isWheelInsideElement(event: WheelEvent, element: HTMLElement): boolean {
  const rect = element.getBoundingClientRect();
  return (
    event.clientX >= rect.left &&
    event.clientX <= rect.right &&
    event.clientY >= rect.top &&
    event.clientY <= rect.bottom
  );
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
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
