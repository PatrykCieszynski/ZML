import { app, BrowserWindow, shell } from "electron";
import { fileURLToPath } from "node:url";
import path from "node:path";

import { resolveDevelopmentAppDataPaths } from "./appDataPaths.ts";
import { registerIpc } from "./ipc/registerIpc";
import { createMainWindow } from "./windows/createMainWindow";
import { createMapWindow } from "./windows/createMapWindow";
import { createOverlayWindow } from "./windows/createOverlayWindow";
import { loadRenderer } from "./windows/loadRenderer";
import { registerWindow } from "./windows/registry";

import { runtime } from "./runtime.ts";
import {
  startAgentEventStream,
  type AgentEventStreamStatus,
  type StopAgentEventStream,
} from "./backend/eventStreamClient.ts";
import { startPositionWsClient } from "./backend/positionWsClient.ts";
import { BackendRestClient } from "./backend/restClient.ts";
import { isUiMockMode } from "./mocks/mockConfig.ts";
import { MockBackendRestClient } from "./mocks/mockBackendRestClient.ts";
import { startMockPositionSource } from "./mocks/mockPositionSource.ts";
import { pushPosition } from "./ipc/pushPosition.ts";
import { pushStatePatch } from "./ipc/pushStatePatch.ts";
import { applyMiningEvent, replaceMiningClaims, replaceMiningDrops } from "./mining/miningDropsState.ts";
import {
  BackendProcessManager,
  createBackendLaunchSpec,
  shouldManageBackend,
} from "./backend/backendProcessManager.ts";
import {
  applyMiningLootEvent,
  replaceMiningLoot,
  replaceMiningLootTotals,
} from "./mining/miningLootState.ts";
import { applyRunEvent, replaceActiveRun, replaceRunSegments } from "./runs/runSegmentsState.ts";
import type { PositionSourceOptions, PositionSourceStatus, StopPositionSource } from "./backend/positionSource.ts";
import { CloudPairingClient } from "./cloud/cloudPairingClient.ts";
import { CloudCredentialStore } from "./cloud/cloudCredentialStore.ts";
import { CloudConnectionService } from "./cloud/cloudConnectionService.ts";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

process.env.APP_ROOT = path.join(__dirname, "..");

if (!app.isPackaged) {
  const devAppData = resolveDevelopmentAppDataPaths(process.env.APP_ROOT);
  app.setPath("userData", devAppData.electron);
  process.env.ZML_APP_DATA_DIR ??= devAppData.backend;
}

export const VITE_DEV_SERVER_URL = process.env["VITE_DEV_SERVER_URL"];
export const MAIN_DIST = path.join(process.env.APP_ROOT, "dist-electron");
export const RENDERER_DIST = path.join(process.env.APP_ROOT, "dist");
export const preloadPath = path.join(MAIN_DIST, "preload.mjs");
process.env.VITE_PUBLIC = VITE_DEV_SERVER_URL ? path.join(process.env.APP_ROOT, "public") : RENDERER_DIST;

const BACKEND_URL = process.env.ZML_BACKEND_URL ?? "http://127.0.0.1:17171";
const CLOUD_GATEWAY_URL = normalizeCloudUrl(
  process.env.ZML_CLOUD_GATEWAY_URL ?? "https://zml-atlas.zabulog.workers.dev",
);
const CLOUD_SYNC_BASE_URL = normalizeCloudUrl(process.env.ZML_CLOUD_BASE_URL ?? CLOUD_GATEWAY_URL);
const UI_MOCKS_ENABLED = isUiMockMode();
const MANAGE_BACKEND = shouldManageBackend({
  mocksEnabled: UI_MOCKS_ENABLED,
  backendUrlOverridden: process.env.ZML_BACKEND_URL !== undefined,
  explicitValue: process.env.ZML_MANAGE_BACKEND,
});
const backendProcessManager = new BackendProcessManager({
  baseUrl: BACKEND_URL,
  launch: createBackendLaunchSpec({
    isPackaged: app.isPackaged,
    resourcesPath: process.resourcesPath,
    appRoot: process.env.APP_ROOT,
  }),
});
const backendRestClient = UI_MOCKS_ENABLED
  ? new MockBackendRestClient()
  : new BackendRestClient({ baseUrl: BACKEND_URL });

let mainWin: BrowserWindow | null = null;
let mapWin: BrowserWindow | null = null;
let overlayWin: BrowserWindow | null = null;
let stopPositionStream: StopPositionSource | null = null;
let stopEventStream: StopAgentEventStream | null = null;
let cloudConnectionService: CloudConnectionService | null = null;
let appIsQuitting = false;
let backendShutdownComplete = false;
let backendShutdownPromise: Promise<void> | null = null;

function handlePositionStatus(status: PositionSourceStatus, err?: string) {
  runtime.agent.status = status;
  runtime.agent.lastError = err || undefined;
  runtime.streams.ws = status === "connected";
  pushStatePatch({
    agent: { ...runtime.agent },
    streams: { ...runtime.streams },
  });
}

function startPositionStream() {
  if (stopPositionStream) return;

  const options: PositionSourceOptions = {
    onStatus: handlePositionStatus,
    onEvent: pushPosition,
  };

  stopPositionStream = UI_MOCKS_ENABLED
    ? startMockPositionSource(options)
    : startPositionWsClient({
        ...options,
        baseUrl: BACKEND_URL,
      });
}

function handleEventStreamStatus(status: AgentEventStreamStatus, err?: string) {
  runtime.streams.sse = status === "connected";
  if (err) runtime.lastError = err;
  pushStatePatch({
    streams: { ...runtime.streams },
  });

  if (status === "connected") {
    void refreshMiningSnapshot();
    void refreshRunSnapshot();
  }
}

async function refreshMiningSnapshot() {
  try {
    const [miningClaims, miningDrops, miningLoot, miningLootTotals] = await Promise.all([
      backendRestClient.listMiningClaims({ active: false, activeRun: true }),
      backendRestClient.listMiningDrops({ activeRun: true }),
      backendRestClient.listMiningLoot({ activeRun: true }),
      backendRestClient.listMiningLootTotals({ activeRun: true }),
    ]);
    replaceMiningClaims(miningClaims);
    replaceMiningDrops(miningDrops);
    replaceMiningLoot(miningLoot);
    replaceMiningLootTotals(miningLootTotals);
  } catch (error) {
    runtime.lastError = error instanceof Error ? error.message : String(error);
    pushStatePatch({
      streams: { ...runtime.streams },
    });
  }
}

async function refreshRunSnapshot() {
  try {
    const [activeRun, runs] = await Promise.all([
      backendRestClient.getActiveRun(),
      backendRestClient.listRuns(),
    ]);
    const runSegments = activeRun === null
      ? []
      : await backendRestClient.listActiveRunSegments();
    runtime.runs = runs;
    replaceActiveRun(activeRun);
    replaceRunSegments(runSegments);
    pushStatePatch({ runs });
  } catch (error) {
    runtime.lastError = error instanceof Error ? error.message : String(error);
    pushStatePatch({
      agent: { ...runtime.agent },
    });
  }
}

async function refreshMiningToolSnapshot() {
  try {
    const [miningTools, activeMiningTools] = await Promise.all([
      backendRestClient.listMiningTools(),
      backendRestClient.getActiveMiningTools(),
    ]);
    runtime.miningTools = miningTools;
    runtime.activeMiningTools = activeMiningTools;
    pushStatePatch({ miningTools, activeMiningTools });
  } catch (error) {
    runtime.lastError = error instanceof Error ? error.message : String(error);
    pushStatePatch({
      agent: { ...runtime.agent },
    });
  }
}

function startEventStream() {
  if (stopEventStream) return;

  if (UI_MOCKS_ENABLED) {
    handleEventStreamStatus("connecting");
    handleEventStreamStatus("connected");
    stopEventStream = () => handleEventStreamStatus("disconnected");
    return;
  }

  stopEventStream = startAgentEventStream({
    baseUrl: BACKEND_URL,
    onStatus: handleEventStreamStatus,
    onEvent: applyAgentEvent,
  });
}

function applyAgentEvent(event: Parameters<typeof applyMiningEvent>[0]): void {
  applyMiningEvent(event);
  applyMiningLootEvent(event);
  applyRunEvent(event);
}

function stopPositionStreamIfRunning() {
  stopPositionStream?.();
  stopPositionStream = null;
  stopEventStream?.();
  stopEventStream = null;
}

async function applyCloudCredential(
  token: string | null,
  applyToRunningBackend: boolean,
): Promise<void> {
  backendProcessManager.setEnvironmentOverride(
    "ZML_CLOUD_BASE_URL",
    token === null ? undefined : CLOUD_SYNC_BASE_URL,
  );
  backendProcessManager.setEnvironmentOverride(
    "ZML_CLOUD_SYNC_TOKEN",
    token === null ? undefined : token,
  );

  if (!applyToRunningBackend) return;
  if (!MANAGE_BACKEND || backendProcessManager.isExternalBackend()) {
    throw new Error("Cannot update cloud credentials for an external Backend");
  }

  await configureRunningBackendCloudSync(token);
}

async function configureRunningBackendCloudSync(token: string | null): Promise<void> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5_000);
  try {
    const response = await fetch(new URL("/api/v1/runtime/cloud-sync", BACKEND_URL), {
      method: "PUT",
      headers: {
        accept: "application/json",
        "content-type": "application/json",
      },
      body: JSON.stringify({
        base_url: token === null ? null : CLOUD_SYNC_BASE_URL,
        token,
      }),
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error(`Backend cloud sync configuration failed (${response.status})`);
    }
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      throw new Error("Backend cloud sync configuration timed out");
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

function updateCloudState(state: ReturnType<CloudConnectionService["getState"]>): void {
  runtime.cloud = state;
  pushStatePatch({ cloud: state });
}

function createCloudConnectionService(): CloudConnectionService {
  return new CloudConnectionService({
    pairingClient: new CloudPairingClient({ baseUrl: CLOUD_GATEWAY_URL }),
    credentialStore: new CloudCredentialStore(
      path.join(app.getPath("userData"), "cloud-credential.json"),
    ),
    approvalBaseUrl: CLOUD_GATEWAY_URL,
    openExternal: async (url) => {
      await shell.openExternal(url);
    },
    applyCredential: applyCloudCredential,
    canApplyCredential: () => MANAGE_BACKEND && !backendProcessManager.isExternalBackend(),
    onState: updateCloudState,
    environmentToken: process.env.ZML_CLOUD_SYNC_TOKEN,
  });
}

function updateWindowVisibilityState(): void {
  runtime.mapWindowVisible = Boolean(mainWin && !mainWin.isDestroyed() && mainWin.isVisible());
  runtime.overlayWindowVisible = Boolean(overlayWin && !overlayWin.isDestroyed() && overlayWin.isVisible());
  pushStatePatch({
    mapWindowVisible: runtime.mapWindowVisible,
    overlayWindowVisible: runtime.overlayWindowVisible,
  });
}

async function ensureMapWindow(): Promise<BrowserWindow> {
  if (mapWin && !mapWin.isDestroyed()) return mapWin;
  mapWin = createMapWindow(preloadPath);
  registerWindow("map", mapWin);
  wireHideOnClose(mapWin);
  await loadRenderer(mapWin, "map");
  if (VITE_DEV_SERVER_URL) mapWin.webContents.openDevTools({ mode: "detach" });
  updateWindowVisibilityState();
  return mapWin;
}

async function ensureOverlayWindow(): Promise<BrowserWindow> {
  if (overlayWin && !overlayWin.isDestroyed()) return overlayWin;
  overlayWin = createOverlayWindow(preloadPath);
  registerWindow("overlay", overlayWin);
  wireHideOnClose(overlayWin);
  await loadRenderer(overlayWin, "overlay");
  updateWindowVisibilityState();
  return overlayWin;
}

async function toggleMapWindow(): Promise<boolean> {
  const win = await ensureMapWindow();
  if (win.isVisible()) {
    win.hide();
  } else {
    win.show();
    win.focus();
  }
  updateWindowVisibilityState();
  return win.isVisible();
}

async function toggleOverlayWindow(): Promise<boolean> {
  const win = await ensureOverlayWindow();
  if (win.isVisible()) {
    win.hide();
  } else {
    win.show();
    win.focus();
  }
  updateWindowVisibilityState();
  return win.isVisible();
}

function wireHideOnClose(win: BrowserWindow): void {
  win.on("close", (event) => {
    if (appIsQuitting) return;
    event.preventDefault();
    win.hide();
    updateWindowVisibilityState();
  });
  win.on("show", updateWindowVisibilityState);
  win.on("hide", updateWindowVisibilityState);
}

async function createWindows() {
  if (cloudConnectionService === null) {
    throw new Error("Cloud connection service is not initialized");
  }
  registerIpc({
    backendRestClient,
    toggleMapWindow,
    toggleOverlayWindow,
    cloudConnectionService,
  });

  mainWin = createMainWindow(preloadPath);
  registerWindow("main", mainWin);
  mainWin.on("closed", () => {
    mainWin = null;
    if (!appIsQuitting && process.platform !== "darwin") app.quit();
  });
  await loadRenderer(mainWin, "main");
  if (VITE_DEV_SERVER_URL) mainWin.webContents.openDevTools({ mode: "detach" });

  await ensureMapWindow();
  await ensureOverlayWindow();

  startPositionStream();
  startEventStream();
  void refreshRunSnapshot();
  void refreshMiningToolSnapshot();
}

async function startApplication(): Promise<void> {
  cloudConnectionService = createCloudConnectionService();
  await cloudConnectionService.restore();

  const backendStartup = MANAGE_BACKEND
    ? backendProcessManager.start().catch((error: unknown) => {
        console.error("[backend] failed to start managed backend", error);
        return false;
      })
    : Promise.resolve(false);
  await createWindows();
  await backendStartup;
}

app.on("before-quit", (event) => {
  if (!MANAGE_BACKEND || backendShutdownComplete) {
    appIsQuitting = true;
    stopPositionStreamIfRunning();
    return;
  }

  event.preventDefault();
  appIsQuitting = true;
  stopPositionStreamIfRunning();
  if (backendShutdownPromise !== null) return;

  backendShutdownPromise = backendProcessManager.stop().finally(() => {
    backendShutdownComplete = true;
    app.quit();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
    mainWin = null;
    mapWin = null;
    overlayWin = null;
  }
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    void createWindows();
  }
});

void app.whenReady().then(startApplication).catch((error: unknown) => {
  console.error("Application startup failed", error);
  app.quit();
});

function normalizeCloudUrl(value: string): string {
  return value.trim().replace(/\/+$/, "");
}
