import { useEffect, useSyncExternalStore } from "react";
import type {
  AgentHealthDto,
  BootstrapAgentState,
  BootstrapState,
  BootstrapStreamsState,
  MiningDropDto,
  OcrPositionDTO,
  OcrPositionEvent,
  RunDto,
  WindowType,
} from "@zml/shared";
import { getZml } from "../zml";

export type ZmlRendererState = {
  windowType: WindowType | null;
  bootstrapped: boolean;
  bootstrapping: boolean;
  agent: BootstrapAgentState;
  streams: BootstrapStreamsState;
  position?: OcrPositionDTO;
  positionEvent?: OcrPositionEvent;
  activeRun?: RunDto;
  miningDrops: MiningDropDto[];
  agentHealth?: AgentHealthDto;
  agentHealthChecking: boolean;
  runCommandPending: boolean;
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
  miningDrops: [],
  agentHealthChecking: false,
  runCommandPending: false,
  lastCommandError: null,
  error: null,
};

let state = initialState;
let initializedFor: WindowType | null = null;
let positionUnsubscribe: (() => void) | null = null;
let statePatchUnsubscribe: (() => void) | null = null;
let bootstrapRequestId = 0;

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
    miningDrops: bootstrap.miningDrops ?? state.miningDrops,
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
    setState({
      activeRun,
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
    const activeRun = await api.stopRun(state.activeRun ? { runId: state.activeRun.runId } : {});
    setState({
      activeRun,
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
