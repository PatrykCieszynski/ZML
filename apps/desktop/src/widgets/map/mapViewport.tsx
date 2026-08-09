import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent,
} from "react";
import DeckGL from "@deck.gl/react";
import {
  OrthographicView,
  type OrthographicViewState,
  type ViewStateChangeParameters,
} from "@deck.gl/core";
import {
  MAP_CONFIG,
  getMapSizePx,
  type MiningClaimDto,
  type MiningDropDto,
  type PlanetId,
} from "@desktop/shared";
import { createClaimPointLayer, createClaimTimerLayer } from "./layers/claimLayers";
import {
  createHexGridLayer,
  createHexGuideLabelLayer,
  createHexGuideLineLayer,
  type MapHexCell,
  type MapHexGuideLine,
} from "./layers/hexGridLayer";
import { createMapTileLayer } from "./layers/mapTileLayer";
import { createMiningDropRadiusLayer } from "./layers/miningDropLayers";
import { createPlayerMarkerLayer, createPlayerRangeLayer } from "./layers/playerLayers";
import { compactLayers } from "./mapLayerUtils";
import {
  createInitialMapViewState,
  coordRadiusToDeckRadius,
  entropiaToDeckPosition,
  type DeckPosition,
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
const DEFAULT_DROP_RADIUS_TTL_MINUTES = 30;
const MAP_MIN_ZOOM = -2.5;
const MAP_MAX_ZOOM = 6;
const MAP_WHEEL_ZOOM_SPEED = 0.0016;
const MAP_WHEEL_ZOOM_EASE = 0.22;
const MAP_WHEEL_ZOOM_SETTLE_THRESHOLD = 0.003;
const HEX_GRID_RING_COUNT = 18;
const SQRT3 = Math.sqrt(3);

type HexGridMode = "no-overlap" | "max-coverage";
type HexGridAnchor = "map" | "player-offset";
type HexGridOrientation = "vertical" | "horizontal";
type HexGridAnchorPoint = EntropiaMapPoint & {
  planetName?: string;
};

function nowSec(): number {
  return Math.floor(Date.now() / 1000);
}

export function MapViewport({
  planetId,
  point,
  miningClaims,
  miningDrops,
  playerRadiusM,
  dropRadiusTtlMinutes = DEFAULT_DROP_RADIUS_TTL_MINUTES,
  hexGridEnabled = false,
  hexGridMode = "max-coverage",
  hexGridAnchor = "map",
  hexGridAnchorPoint = null,
  hexGridOrientation = "vertical",
  followPlayer,
  onFollowPlayerChange,
  onIgnoreClaim,
  onMarkClaimDepleted,
}: {
  planetId: PlanetId;
  point: EntropiaMapPoint | null;
  miningClaims: readonly MiningClaimDto[];
  miningDrops: readonly MiningDropDto[];
  playerRadiusM?: number | null;
  dropRadiusTtlMinutes?: number | null;
  hexGridEnabled?: boolean;
  hexGridMode?: HexGridMode;
  hexGridAnchor?: HexGridAnchor;
  hexGridAnchorPoint?: HexGridAnchorPoint | null;
  hexGridOrientation?: HexGridOrientation;
  followPlayer: boolean;
  onFollowPlayerChange: (followPlayer: boolean) => void;
  onIgnoreClaim?: (claimId: string) => void | Promise<void>;
  onMarkClaimDepleted?: (claimId: string) => void | Promise<void>;
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
  const [claimMenu, setClaimMenu] = useState<{
    claim: MapClaim;
    x: number;
    y: number;
  } | null>(null);

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
    () => {
      const ttlMinutes = dropRadiusTtlMinutes ?? DEFAULT_DROP_RADIUS_TTL_MINUTES;
      const cutoffTsMs = ttlMinutes <= 0 ? null : (currentSec - ttlMinutes * 60) * 1000;

      return miningDrops.flatMap((drop) => {
        if (cutoffTsMs !== null && drop.observedTsMs < cutoffTsMs) return [];
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
      });
    },
    [currentSec, dropRadiusTtlMinutes, miningDrops, planetId],
  );
  const playerRangeRadiusM = useMemo(
    () =>
      playerRadiusM ??
      miningDrops.find((drop) => isDropOnPlanet(planetId, drop))?.dropRadiusM ??
      DEFAULT_PLAYER_RADIUS_M,
    [miningDrops, planetId, playerRadiusM],
  );
  const hexGridCells = useMemo(
    () =>
      createHexGridCells({
        planetId,
        anchorPoint: hexGridAnchorPoint,
        radiusM: playerRangeRadiusM,
        enabled: hexGridEnabled,
        mode: hexGridMode,
        anchor: hexGridAnchor,
        orientation: hexGridOrientation,
      }),
    [
      hexGridAnchor,
      hexGridAnchorPoint,
      hexGridEnabled,
      hexGridMode,
      hexGridOrientation,
      planetId,
      playerRangeRadiusM,
    ],
  );
  const hexGuideLines = useMemo(
    () =>
      createHexGuideLines({
        planetId,
        point,
        marker,
        anchorPoint: hexGridAnchorPoint,
        radiusM: playerRangeRadiusM,
        enabled: hexGridEnabled,
        mode: hexGridMode,
        anchor: hexGridAnchor,
        orientation: hexGridOrientation,
      }),
    [
      hexGridAnchor,
      hexGridAnchorPoint,
      hexGridEnabled,
      hexGridMode,
      hexGridOrientation,
      marker,
      planetId,
      playerRangeRadiusM,
      point,
    ],
  );
  const mapMiningClaims = useMemo<MapClaim[]>(
    () =>
      miningClaims.flatMap((claim) => {
        if (claim.status !== "active" || !claim.position || !isClaimOnPlanet(planetId, claim)) {
          return [];
        }

        const expiresAtSec =
          claim.expectedExpiresTsMs !== null
            ? Math.floor(claim.expectedExpiresTsMs / 1000)
            : null;
        if (expiresAtSec !== null && expiresAtSec <= currentSec) {
          return [];
        }

        return [
          {
            id: claim.claimId,
            x: claim.position.x,
            y: claim.position.y,
            position: entropiaToDeckPosition(planetId, claim.position),
            resourceKind: resourceKindFromName(claim.resourceName),
            resourceName: claim.resourceName,
            sizeLabel: claim.sizeLabel,
            sizeIndex: claim.sizeIndex,
            expiresAtSec,
          },
        ];
      }),
    [currentSec, miningClaims, planetId],
  );
  const hasClaimTimers = useMemo(
    () => mapMiningClaims.some((claim) => claim.expiresAtSec !== null),
    [mapMiningClaims],
  );
  const hasDropRadiusTtl =
    miningDrops.length > 0 &&
    (dropRadiusTtlMinutes ?? DEFAULT_DROP_RADIUS_TTL_MINUTES) > 0;

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
    if (!DEBUG_CLAIMS_ENABLED && !hasClaimTimers && !hasDropRadiusTtl) return;

    const timer = window.setInterval(() => setCurrentSec(nowSec()), 1000);
    return () => window.clearInterval(timer);
  }, [hasClaimTimers, hasDropRadiusTtl]);

  const tileLayer = useMemo(() => createMapTileLayer(planetId), [planetId]);
  const hexGridLayer = useMemo(() => createHexGridLayer(hexGridCells), [hexGridCells]);
  const hexGuideLineLayer = useMemo(
    () => createHexGuideLineLayer(hexGuideLines),
    [hexGuideLines],
  );
  const hexGuideLabelLayer = useMemo(
    () => createHexGuideLabelLayer(hexGuideLines),
    [hexGuideLines],
  );
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
        hexGridLayer,
        hexGuideLineLayer,
        hexGuideLabelLayer,
        miningDropRadiusLayer,
        claimPointLayer,
        claimTimerLayer,
        playerRangeLayer,
        playerMarkerLayer,
      ]),
    [
      claimPointLayer,
      claimTimerLayer,
      hexGuideLabelLayer,
      hexGuideLineLayer,
      hexGridLayer,
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

  const handleContextMenu = (event: MouseEvent<HTMLDivElement>) => {
    event.preventDefault();
    if (activeClaims.length === 0) return;
    const element = mapRootRef.current;
    if (element === null) return;

    const claim = findNearestClaimAtScreenPoint({
      claims: activeClaims,
      element,
      clientX: event.clientX,
      clientY: event.clientY,
      viewState: viewStateRef.current,
    });
    if (claim === null) {
      setClaimMenu(null);
      return;
    }

    const rect = element.getBoundingClientRect();
    setClaimMenu({
      claim,
      x: clamp(event.clientX - rect.left, 8, Math.max(8, rect.width - 192)),
      y: clamp(event.clientY - rect.top, 8, Math.max(8, rect.height - 144)),
    });
  };

  const closeClaimMenu = () => setClaimMenu(null);

  return (
    <div
      ref={mapRootRef}
      onContextMenu={handleContextMenu}
      onPointerDown={(event) => {
        if (event.button !== 2) closeClaimMenu();
      }}
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
      {claimMenu !== null && (
        <div
          className="zml-map-context-menu"
          style={{ left: claimMenu.x, top: claimMenu.y }}
          onPointerDown={(event) => event.stopPropagation()}
        >
          <strong>{claimMenu.claim.resourceName ?? "Unknown claim"}</strong>
          <span>
            {formatClaimMenuSize(claimMenu.claim)} at {Math.round(claimMenu.claim.x)},{" "}
            {Math.round(claimMenu.claim.y)}
          </span>
          <button
            type="button"
            onClick={() => {
              const claimId = claimMenu.claim.id;
              closeClaimMenu();
              void onMarkClaimDepleted?.(claimId);
            }}
            disabled={onMarkClaimDepleted === undefined || claimMenu.claim.id.startsWith("debug-")}
          >
            Mark extracted
          </button>
          <button
            type="button"
            onClick={() => {
              const claimId = claimMenu.claim.id;
              closeClaimMenu();
              void onIgnoreClaim?.(claimId);
            }}
            disabled={onIgnoreClaim === undefined || claimMenu.claim.id.startsWith("debug-")}
          >
            Ignore false claim
          </button>
        </div>
      )}
    </div>
  );
}

function createHexGridCells({
  planetId,
  anchorPoint,
  radiusM,
  enabled,
  mode,
  anchor,
  orientation,
}: {
  planetId: PlanetId;
  anchorPoint: HexGridAnchorPoint | null;
  radiusM: number;
  enabled: boolean;
  mode: HexGridMode;
  anchor: HexGridAnchor;
  orientation: HexGridOrientation;
}): MapHexCell[] {
  if (!enabled || radiusM <= 0) return [];

  const anchorPosition = getHexGridAnchorPosition(planetId, anchorPoint, anchor);
  if (anchorPosition === null) return [];

  const spacingFactor = mode === "no-overlap" ? 2 : SQRT3;
  const spacingPx = coordRadiusToDeckRadius(planetId, radiusM * spacingFactor);
  if (spacingPx <= 0) return [];

  const hexRadiusPx = spacingPx / SQRT3;
  const { width, height } = getMapSizePx(MAP_CONFIG, planetId);
  const cells: MapHexCell[] = [];

  for (let q = -HEX_GRID_RING_COUNT; q <= HEX_GRID_RING_COUNT; q += 1) {
    const rMin = Math.max(-HEX_GRID_RING_COUNT, -q - HEX_GRID_RING_COUNT);
    const rMax = Math.min(HEX_GRID_RING_COUNT, -q + HEX_GRID_RING_COUNT);
    for (let r = rMin; r <= rMax; r += 1) {
      const [dx, dy] = hexGridOffset(q, r, spacingPx, orientation);
      const center: DeckPosition = [anchorPosition[0] + dx, anchorPosition[1] + dy, 0];
      if (!isHexNearMap(center, width, height, hexRadiusPx)) continue;
      cells.push({
        id: `${q}:${r}`,
        path: createHexPath(center, hexRadiusPx, orientation),
      });
    }
  }

  return cells;
}

function createHexGuideLines({
  planetId,
  point,
  marker,
  anchorPoint,
  radiusM,
  enabled,
  mode,
  anchor,
  orientation,
}: {
  planetId: PlanetId;
  point: EntropiaMapPoint | null;
  marker: DeckPoint | null;
  anchorPoint: HexGridAnchorPoint | null;
  radiusM: number;
  enabled: boolean;
  mode: HexGridMode;
  anchor: HexGridAnchor;
  orientation: HexGridOrientation;
}): MapHexGuideLine[] {
  if (!enabled || point === null || marker === null || radiusM <= 0) return [];

  const anchorPosition = getHexGridAnchorPosition(planetId, anchorPoint, anchor);
  if (anchorPosition === null) return [];

  const spacingFactor = mode === "no-overlap" ? 2 : SQRT3;
  const spacingPx = coordRadiusToDeckRadius(planetId, radiusM * spacingFactor);
  if (spacingPx <= 0) return [];

  const [localX, localY] = [
    marker.position[0] - anchorPosition[0],
    marker.position[1] - anchorPosition[1],
  ];
  const rounded = roundAxial(hexGridFractionalAxial(localX, localY, spacingPx, orientation));
  const [centerOffsetX, centerOffsetY] = hexGridOffset(
    rounded.q,
    rounded.r,
    spacingPx,
    orientation,
  );
  const center: DeckPosition = [
    anchorPosition[0] + centerOffsetX,
    anchorPosition[1] + centerOffsetY,
    0,
  ];
  const xTarget: DeckPosition = [center[0], marker.position[1], 0];
  const yTarget: DeckPosition = [marker.position[0], center[1], 0];
  const centerPoint = deckToEntropiaPoint(planetId, center);
  const offsetX = point.x - centerPoint.x;
  const offsetY = point.y - centerPoint.y;

  return [
    {
      id: "hex-guide-x",
      axis: "x",
      path: [marker.position, xTarget],
      label: `X ${formatSignedCoordOffset(offsetX)}`,
      labelPosition: midpoint(marker.position, xTarget),
      labelPixelOffset: [offsetX >= 0 ? 18 : -18, -10],
    },
    {
      id: "hex-guide-y",
      axis: "y",
      path: [marker.position, yTarget],
      label: `Y ${formatSignedCoordOffset(offsetY)}`,
      labelPosition: midpoint(marker.position, yTarget),
      labelPixelOffset: [12, offsetY >= 0 ? -16 : 16],
    },
    ...createDashedGuideLine("hex-guide-diagonal", marker.position, center),
  ];
}

function createDashedGuideLine(
  id: string,
  start: DeckPosition,
  end: DeckPosition,
): MapHexGuideLine[] {
  const dashLengthPx = 18;
  const gapLengthPx = 10;
  const distancePx = Math.hypot(end[0] - start[0], end[1] - start[1]);
  if (distancePx <= 0) return [];

  const segments: MapHexGuideLine[] = [];
  for (
    let segmentStartPx = 0, index = 0;
    segmentStartPx < distancePx;
    segmentStartPx += dashLengthPx + gapLengthPx, index += 1
  ) {
    const segmentEndPx = Math.min(segmentStartPx + dashLengthPx, distancePx);
    segments.push({
      id: `${id}-${index}`,
      axis: "diagonal",
      path: [
        interpolateDeckPosition(start, end, segmentStartPx / distancePx),
        interpolateDeckPosition(start, end, segmentEndPx / distancePx),
      ],
    });
  }
  return segments;
}

function interpolateDeckPosition(
  start: DeckPosition,
  end: DeckPosition,
  ratio: number,
): DeckPosition {
  return [
    start[0] + (end[0] - start[0]) * ratio,
    start[1] + (end[1] - start[1]) * ratio,
    start[2] + (end[2] - start[2]) * ratio,
  ];
}

function getHexGridAnchorPosition(
  planetId: PlanetId,
  anchorPoint: HexGridAnchorPoint | null,
  anchor: HexGridAnchor,
): DeckPosition | null {
  if (anchor === "player-offset") {
    if (anchorPoint === null || !isPointOnPlanet(planetId, anchorPoint)) return null;
    return entropiaToDeckPosition(planetId, anchorPoint);
  }

  const { width, height } = getMapSizePx(MAP_CONFIG, planetId);
  return [width / 2, height / 2, 0];
}

function isPointOnPlanet(planetId: PlanetId, point: HexGridAnchorPoint): boolean {
  const planetName = point.planetName;
  if (!planetName) return true;
  return planetName.toLowerCase() === planetId;
}

function hexGridFractionalAxial(
  localX: number,
  localY: number,
  spacingPx: number,
  orientation: HexGridOrientation,
): { q: number; r: number } {
  if (orientation === "vertical") {
    const r = localY / (spacingPx * (SQRT3 / 2));
    const q = localX / spacingPx - r / 2;
    return { q, r };
  }

  const q = localX / (spacingPx * (SQRT3 / 2));
  const r = localY / spacingPx - q / 2;
  return { q, r };
}

function roundAxial({ q, r }: { q: number; r: number }): { q: number; r: number } {
  const cubeX = q;
  const cubeZ = r;
  const cubeY = -cubeX - cubeZ;

  const rx = Math.round(cubeX);
  const ry = Math.round(cubeY);
  const rz = Math.round(cubeZ);

  const xDiff = Math.abs(rx - cubeX);
  const yDiff = Math.abs(ry - cubeY);
  const zDiff = Math.abs(rz - cubeZ);

  if (xDiff > yDiff && xDiff > zDiff) {
    return { q: -ry - rz, r: rz };
  }

  if (zDiff > yDiff) {
    return { q: rx, r: -rx - ry };
  }

  return { q: rx, r: rz };
}

function hexGridOffset(
  q: number,
  r: number,
  spacingPx: number,
  orientation: HexGridOrientation,
): readonly [number, number] {
  if (orientation === "vertical") {
    return [
      spacingPx * (q + r / 2),
      spacingPx * (SQRT3 / 2) * r,
    ];
  }

  return [
    spacingPx * (SQRT3 / 2) * q,
    spacingPx * (r + q / 2),
  ];
}

function deckToEntropiaPoint(planetId: PlanetId, position: DeckPosition): EntropiaMapPoint {
  const planet = MAP_CONFIG.planets[planetId];
  const { width, height } = getMapSizePx(MAP_CONFIG, planetId);
  const lonRange = planet.maxLon - planet.minLon;
  const latRange = planet.maxLat - planet.minLat;
  if (width <= 0 || height <= 0 || lonRange <= 0 || latRange <= 0) {
    return { x: 0, y: 0 };
  }

  return {
    x: planet.minLon + (position[0] / width) * lonRange,
    y: planet.minLat + ((height - position[1]) / height) * latRange,
  };
}

function midpoint(left: DeckPosition, right: DeckPosition): DeckPosition {
  return [
    (left[0] + right[0]) / 2,
    (left[1] + right[1]) / 2,
    0,
  ];
}

function findNearestClaimAtScreenPoint({
  claims,
  element,
  clientX,
  clientY,
  viewState,
}: {
  claims: readonly MapClaim[];
  element: HTMLElement;
  clientX: number;
  clientY: number;
  viewState: OrthographicViewState;
}): MapClaim | null {
  const rect = element.getBoundingClientRect();
  const scale = 2 ** readZoom(viewState.zoom);
  const target = Array.isArray(viewState.target)
    ? viewState.target
    : [0, 0, 0];
  const worldX = target[0] + (clientX - rect.left - rect.width / 2) / scale;
  const worldY = target[1] + (clientY - rect.top - rect.height / 2) / scale;
  const maxDistancePx = 14;
  let nearest: { claim: MapClaim; distancePx: number } | null = null;

  for (const claim of claims) {
    const distanceWorld = Math.hypot(claim.position[0] - worldX, claim.position[1] - worldY);
    const distancePx = distanceWorld * scale;
    if (distancePx > maxDistancePx) continue;
    if (nearest === null || distancePx < nearest.distancePx) {
      nearest = { claim, distancePx };
    }
  }

  return nearest?.claim ?? null;
}

function formatClaimMenuSize(claim: MapClaim): string {
  if (claim.sizeLabel === null && claim.sizeIndex === null) return "Claim";
  if (claim.sizeLabel === null) return `Size ${claim.sizeIndex}`;
  if (claim.sizeIndex === null) return claim.sizeLabel;
  return `${claim.sizeLabel} ${claim.sizeIndex}`;
}

function formatSignedCoordOffset(value: number): string {
  const rounded = Math.round(value);
  return rounded >= 0 ? `+${rounded}` : String(rounded);
}

function createHexPath(
  center: DeckPosition,
  radiusPx: number,
  orientation: HexGridOrientation,
): DeckPosition[] {
  const angleOffsetDeg = orientation === "vertical" ? 30 : 0;
  const path: DeckPosition[] = [];

  for (let index = 0; index <= 6; index += 1) {
    const angle = ((angleOffsetDeg + index * 60) * Math.PI) / 180;
    path.push([
      center[0] + Math.cos(angle) * radiusPx,
      center[1] + Math.sin(angle) * radiusPx,
      0,
    ]);
  }

  return path;
}

function isHexNearMap(
  center: DeckPosition,
  width: number,
  height: number,
  radiusPx: number,
): boolean {
  return (
    center[0] >= -radiusPx &&
    center[0] <= width + radiusPx &&
    center[1] >= -radiusPx &&
    center[1] <= height + radiusPx
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
