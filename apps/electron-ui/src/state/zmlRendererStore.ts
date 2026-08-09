import { useEffect, useSyncExternalStore } from "react";
import type {
  AgentHealthDto,
  ActiveMiningToolsDto,
  BootstrapAgentState,
  BootstrapState,
  BootstrapStreamsState,
  CreateMiningToolProfileRequest,
  MiningClaimDto,
  MiningDropDto,
  MiningLootItemDto,
  MiningLootTotalDto,
  MiningToolProfileDto,
  OcrPositionDTO,
  OcrPositionEvent,
  RunDto,
  RunSegmentDto,
  SetActiveMiningToolsRequest,
  WindowType,
} from "@desktop/shared";
import { getZml } from "../zml";

export type ZmlRendererState = {
  windowType: WindowType | null;
  bootstrapped: boolean;
  bootstrapping: boolean;
  agent: BootstrapAgentState;
  streams: BootstrapStreamsState;
  position?: OcrPositionDTO;
  positionEvent?: OcrPositionEvent;
  mapWindowVisible: boolean;
  overlayWindowVisible: boolean;
  activeRun: RunDto | null;
  runs: RunDto[];
  runSegments: RunSegmentDto[];
  miningClaims: MiningClaimDto[];
  miningDrops: MiningDropDto[];
  miningLoot: MiningLootItemDto[];
  miningLootTotals: MiningLootTotalDto[];
  miningTools: MiningToolProfileDto[];
  activeMiningTools?: ActiveMiningToolsDto;
  agentHealth?: AgentHealthDto;
  agentHealthChecking: boolean;
  runCommandPending: boolean;
  miningToolsLoading: boolean;
  toolCommandPending: boolean;
  lastCommandError: string | null;
  error: string | null;
  lastBootstrapTsMs?: number;
};

const initialState: ZmlRendererState = {
  windowType: null,
  bootstrapped: false,
  bootstrapping: false,
  agent: { status: "connecting" },
  streams: { ws: false, sse: false },
  mapWindowVisible: false,
  overlayWindowVisible: false,
  activeRun: null,
  runs: [],
  runSegments: [],
  miningClaims: [],
  miningDrops: [],
  miningLoot: [],
  miningLootTotals: [],
  miningTools: [],
  activeMiningTools: undefined,
  agentHealthChecking: false,
  runCommandPending: false,
  miningToolsLoading: false,
  toolCommandPending: false,
  lastCommandError: null,
  error: null,
};

let state = initialState;
let initializedFor: WindowType | null = null;
let positionUnsubscribe: (() => void) | null = null;
let statePatchUnsubscribe: (() => void) | null = null;
let bootstrapRequestId = 0;
let lastMainPositionUpdateTsMs = 0;

const MAIN_POSITION_UPDATE_INTERVAL_MS = 1_000;

const listeners = new Set<() => void>();

function emit(): void {
  for (const listener of listeners) listener();
}

function setState(patch: Partial<ZmlRendererState>): void {
  state = { ...state, ...patch };
  emit();
}

function errorToMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function applyBootstrap(bootstrap: BootstrapState): void {
  setState({
    windowType: bootstrap.windowType,
    bootstrapped: true,
    bootstrapping: false,
    agent: bootstrap.agent,
    streams: bootstrap.streams,
    position: bootstrap.position ?? state.position,
    mapWindowVisible: bootstrap.mapWindowVisible ?? state.mapWindowVisible,
    overlayWindowVisible: bootstrap.overlayWindowVisible ?? state.overlayWindowVisible,
    activeRun: bootstrap.activeRun ?? null,
    runs: bootstrap.runs ?? state.runs,
    runSegments: bootstrap.runSegments ?? state.runSegments,
    miningClaims: bootstrap.miningClaims ?? state.miningClaims,
    miningDrops: bootstrap.miningDrops ?? state.miningDrops,
    miningLoot: bootstrap.miningLoot ?? state.miningLoot,
    miningLootTotals: bootstrap.miningLootTotals ?? state.miningLootTotals,
    miningTools: bootstrap.miningTools ?? state.miningTools,
    activeMiningTools: bootstrap.activeMiningTools ?? state.activeMiningTools,
    error: null,
    lastBootstrapTsMs: bootstrap.nowTsMs,
  });
}

export function getZmlRendererSnapshot(): ZmlRendererState {
  return state;
}

export function subscribeZmlRendererStore(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function initZmlRendererStore(windowType: WindowType): void {
  if (initializedFor === windowType && positionUnsubscribe !== null) return;

  if (initializedFor !== null && initializedFor !== windowType) {
    positionUnsubscribe?.();
    statePatchUnsubscribe?.();
    positionUnsubscribe = null;
    statePatchUnsubscribe = null;
  }

  initializedFor = windowType;
  const requestId = ++bootstrapRequestId;
  lastMainPositionUpdateTsMs = 0;

  let api;
  try {
    api = getZml();
  } catch (error) {
    setState({
      windowType,
      bootstrapping: false,
      error: errorToMessage(error),
    });
    return;
  }

  setState({
    windowType,
    bootstrapping: true,
    error: null,
  });

  void api
    .getBootstrapState(windowType)
    .then((bootstrap) => {
      if (requestId !== bootstrapRequestId) return;
      applyBootstrap(bootstrap);
    })
    .catch((error: unknown) => {
      if (requestId !== bootstrapRequestId) return;
      setState({
        bootstrapping: false,
        error: errorToMessage(error),
      });
    });

  positionUnsubscribe = api.onPosition((event) => {
    const nowTsMs = Date.now();
    const isMainWindow = initializedFor === "main";
    if (
      isMainWindow &&
      state.position !== undefined &&
      nowTsMs - lastMainPositionUpdateTsMs < MAIN_POSITION_UPDATE_INTERVAL_MS
    ) {
      return;
    }

    if (isMainWindow) {
      lastMainPositionUpdateTsMs = nowTsMs;
    }

    setState({
      positionEvent: event,
      position: event.payload,
      error: null,
    });
  });

  statePatchUnsubscribe = api.onStatePatch((patch) => {
    setState({
      ...patch,
      error: null,
    });
  });
}

export async function refreshAgentHealth(): Promise<void> {
  let api;
  try {
    api = getZml();
  } catch (error) {
    setState({
      agentHealthChecking: false,
      lastCommandError: errorToMessage(error),
    });
    return;
  }

  setState({
    agentHealthChecking: true,
    lastCommandError: null,
  });

  try {
    const agentHealth = await api.getAgentHealth();
    setState({
      agentHealth,
      agentHealthChecking: false,
      lastCommandError: null,
    });
  } catch (error) {
    setState({
      agentHealthChecking: false,
      lastCommandError: errorToMessage(error),
    });
  }
}

export async function startRun(name: string): Promise<void> {
  let api;
  try {
    api = getZml();
  } catch (error) {
    setState({
      runCommandPending: false,
      lastCommandError: errorToMessage(error),
    });
    return;
  }

  const trimmedName = name.trim();
  if (!trimmedName) {
    setState({ lastCommandError: "Run name is required" });
    return;
  }

  setState({
    runCommandPending: true,
    lastCommandError: null,
  });

  try {
    const activeRun = await api.startRun({ name: trimmedName });
    const runs = await api.listRuns();
    setState({
      activeRun,
      runs,
      runSegments: [],
      runCommandPending: false,
      lastCommandError: null,
    });
  } catch (error) {
    setState({
      runCommandPending: false,
      lastCommandError: errorToMessage(error),
    });
  }
}

export async function refreshRunState(): Promise<void> {
  let api;
  try {
    api = getZml();
  } catch (error) {
    setState({
      lastCommandError: errorToMessage(error),
    });
    return;
  }

  try {
    const activeRun = await api.getActiveRun();
    const [runs, runSegments] = await Promise.all([
      api.listRuns(),
      activeRun === null ? Promise.resolve([]) : api.listActiveRunSegments(),
    ]);
    setState({
      activeRun,
      runs,
      runSegments,
      lastCommandError: null,
    });
  } catch (error) {
    setState({
      lastCommandError: errorToMessage(error),
    });
  }
}

export async function stopRun(): Promise<void> {
  let api;
  try {
    api = getZml();
  } catch (error) {
    setState({
      runCommandPending: false,
      lastCommandError: errorToMessage(error),
    });
    return;
  }

  setState({
    runCommandPending: true,
    lastCommandError: null,
  });

  try {
    await api.stopRun(state.activeRun ? { runId: state.activeRun.runId } : {});
    const runs = await api.listRuns();
    setState({
      activeRun: null,
      runs,
      runSegments: [],
      runCommandPending: false,
      lastCommandError: null,
    });
  } catch (error) {
    setState({
      runCommandPending: false,
      lastCommandError: errorToMessage(error),
    });
  }
}

export async function ignoreMiningClaim(claimId: string): Promise<void> {
  let api;
  try {
    api = getZml();
  } catch (error) {
    setState({
      lastCommandError: errorToMessage(error),
    });
    return;
  }

  setState({ lastCommandError: null });

  try {
    const claim = await api.ignoreMiningClaim(claimId);
    setState({
      miningClaims: upsertMiningClaim(state.miningClaims, claim),
      lastCommandError: null,
    });
  } catch (error) {
    setState({
      lastCommandError: errorToMessage(error),
    });
  }
}

export async function markMiningClaimDepleted(claimId: string): Promise<void> {
  let api;
  try {
    api = getZml();
  } catch (error) {
    setState({
      lastCommandError: errorToMessage(error),
    });
    return;
  }

  setState({ lastCommandError: null });

  try {
    const claim = await api.markMiningClaimDepleted(claimId);
    setState({
      miningClaims: upsertMiningClaim(state.miningClaims, claim),
      lastCommandError: null,
    });
  } catch (error) {
    setState({
      lastCommandError: errorToMessage(error),
    });
  }
}

export async function refreshMiningTools(): Promise<void> {
  let api;
  try {
    api = getZml();
  } catch (error) {
    setState({
      miningToolsLoading: false,
      lastCommandError: errorToMessage(error),
    });
    return;
  }

  setState({
    miningToolsLoading: true,
    lastCommandError: null,
  });

  try {
    const [miningTools, activeMiningTools] = await Promise.all([
      api.listMiningTools(),
      api.getActiveMiningTools(),
    ]);
    setState({
      miningTools,
      activeMiningTools,
      miningToolsLoading: false,
      lastCommandError: null,
    });
  } catch (error) {
    setState({
      miningToolsLoading: false,
      lastCommandError: errorToMessage(error),
    });
  }
}

export async function refreshRuns(): Promise<void> {
  let api;
  try {
    api = getZml();
  } catch (error) {
    setState({ lastCommandError: errorToMessage(error) });
    return;
  }

  try {
    const runs = await api.listRuns();
    setState({ runs, lastCommandError: null });
  } catch (error) {
    setState({ lastCommandError: errorToMessage(error) });
  }
}

export async function resumeRun(runId: number): Promise<void> {
  let api;
  try {
    api = getZml();
  } catch (error) {
    setState({
      runCommandPending: false,
      lastCommandError: errorToMessage(error),
    });
    return;
  }

  setState({
    runCommandPending: true,
    lastCommandError: null,
  });

  try {
    const activeRun = await api.resumeRun(runId);
    const [runs, runSegments] = await Promise.all([
      api.listRuns(),
      api.listActiveRunSegments(),
    ]);
    setState({
      activeRun,
      runs,
      runSegments,
      runCommandPending: false,
      lastCommandError: null,
    });
  } catch (error) {
    setState({
      runCommandPending: false,
      lastCommandError: errorToMessage(error),
    });
  }
}

export async function updateRunName(runId: number, name: string): Promise<void> {
  let api;
  try {
    api = getZml();
  } catch (error) {
    setState({
      runCommandPending: false,
      lastCommandError: errorToMessage(error),
    });
    return;
  }

  const trimmedName = name.trim();
  if (!trimmedName) {
    setState({ lastCommandError: "Run name is required" });
    return;
  }

  setState({
    runCommandPending: true,
    lastCommandError: null,
  });

  try {
    const updatedRun = await api.updateRun(runId, { name: trimmedName });
    const runs = await api.listRuns();
    setState({
      activeRun: state.activeRun?.runId === runId ? updatedRun : state.activeRun,
      runs,
      runCommandPending: false,
      lastCommandError: null,
    });
  } catch (error) {
    setState({
      runCommandPending: false,
      lastCommandError: errorToMessage(error),
    });
  }
}

export async function deleteRun(runId: number): Promise<void> {
  let api;
  try {
    api = getZml();
  } catch (error) {
    setState({
      runCommandPending: false,
      lastCommandError: errorToMessage(error),
    });
    return;
  }

  setState({
    runCommandPending: true,
    lastCommandError: null,
  });

  try {
    const deletingActive = state.activeRun?.runId === runId;
    await api.deleteRun(runId);
    const runs = await api.listRuns();
    setState({
      activeRun: deletingActive ? null : state.activeRun,
      runs,
      runSegments: deletingActive ? [] : state.runSegments,
      miningClaims: deletingActive ? [] : state.miningClaims,
      miningDrops: deletingActive ? [] : state.miningDrops,
      miningLoot: deletingActive ? [] : state.miningLoot,
      miningLootTotals: deletingActive ? [] : state.miningLootTotals,
      runCommandPending: false,
      lastCommandError: null,
    });
  } catch (error) {
    setState({
      runCommandPending: false,
      lastCommandError: errorToMessage(error),
    });
  }
}

export async function toggleMapWindow(): Promise<void> {
  let api;
  try {
    api = getZml();
  } catch (error) {
    setState({ lastCommandError: errorToMessage(error) });
    return;
  }

  try {
    const mapWindowVisible = await api.toggleMapWindow();
    setState({ mapWindowVisible, lastCommandError: null });
  } catch (error) {
    setState({ lastCommandError: errorToMessage(error) });
  }
}

export async function toggleOverlayWindow(): Promise<void> {
  let api;
  try {
    api = getZml();
  } catch (error) {
    setState({ lastCommandError: errorToMessage(error) });
    return;
  }

  try {
    const overlayWindowVisible = await api.toggleOverlayWindow();
    setState({ overlayWindowVisible, lastCommandError: null });
  } catch (error) {
    setState({ lastCommandError: errorToMessage(error) });
  }
}

export async function createMiningTool(request: CreateMiningToolProfileRequest): Promise<void> {
  let api;
  try {
    api = getZml();
  } catch (error) {
    setState({
      toolCommandPending: false,
      lastCommandError: errorToMessage(error),
    });
    return;
  }

  setState({
    toolCommandPending: true,
    lastCommandError: null,
  });

  try {
    const profile = await api.createMiningTool(request);
    setState({
      miningTools: upsertMiningTool(state.miningTools, profile),
      toolCommandPending: false,
      lastCommandError: null,
    });
  } catch (error) {
    setState({
      toolCommandPending: false,
      lastCommandError: errorToMessage(error),
    });
  }
}

export async function deleteMiningTool(toolId: string): Promise<void> {
  let api;
  try {
    api = getZml();
  } catch (error) {
    setState({
      toolCommandPending: false,
      lastCommandError: errorToMessage(error),
    });
    return;
  }

  setState({
    toolCommandPending: true,
    lastCommandError: null,
  });

  try {
    await api.deleteMiningTool(toolId);
    const [miningTools, activeMiningTools] = await Promise.all([
      api.listMiningTools(),
      api.getActiveMiningTools(),
    ]);
    setState({
      miningTools,
      activeMiningTools,
      toolCommandPending: false,
      lastCommandError: null,
    });
  } catch (error) {
    setState({
      toolCommandPending: false,
      lastCommandError: errorToMessage(error),
    });
  }
}

export async function setActiveMiningTools(request: SetActiveMiningToolsRequest): Promise<void> {
  let api;
  try {
    api = getZml();
  } catch (error) {
    setState({
      toolCommandPending: false,
      lastCommandError: errorToMessage(error),
    });
    return;
  }

  setState({
    toolCommandPending: true,
    lastCommandError: null,
  });

  try {
    const activeMiningTools = await api.setActiveMiningTools(request);
    setState({
      activeMiningTools,
      toolCommandPending: false,
      lastCommandError: null,
    });
  } catch (error) {
    setState({
      toolCommandPending: false,
      lastCommandError: errorToMessage(error),
    });
  }
}

function sortMiningTools(tools: MiningToolProfileDto[]): MiningToolProfileDto[] {
  const kindOrder = new Map<MiningToolProfileDto["kind"], number>([
    ["finder", 0],
    ["amp", 1],
    ["extractor", 2],
  ]);

  return tools.sort((a, b) => {
    const byKind = (kindOrder.get(a.kind) ?? 99) - (kindOrder.get(b.kind) ?? 99);
    if (byKind !== 0) return byKind;
    return a.name.localeCompare(b.name);
  });
}

function upsertMiningTool(
  tools: readonly MiningToolProfileDto[],
  profile: MiningToolProfileDto,
): MiningToolProfileDto[] {
  return sortMiningTools([
    ...tools.filter((tool) => tool.toolId !== profile.toolId),
    profile,
  ]);
}

function upsertMiningClaim(
  claims: readonly MiningClaimDto[],
  claim: MiningClaimDto,
): MiningClaimDto[] {
  return [
    claim,
    ...claims.filter((item) => item.claimId !== claim.claimId),
  ].sort((a, b) => b.observedTsMs - a.observedTsMs);
}

export function useZmlRendererStore(windowType: WindowType): ZmlRendererState {
  useEffect(() => {
    initZmlRendererStore(windowType);
  }, [windowType]);

  return useSyncExternalStore(
    subscribeZmlRendererStore,
    getZmlRendererSnapshot,
    getZmlRendererSnapshot,
  );
}
