import { app, BrowserWindow } from 'electron'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

import { registerIpc } from "./ipc/registerIpc";
import { createMainWindow } from "./windows/createMainWindow";
import { createMapWindow } from "./windows/createMapWindow";
import { createOverlayWindow } from "./windows/createOverlayWindow";
import { loadRenderer } from "./windows/loadRenderer";
import { registerWindow } from "./windows/registry";

import {runtime} from "./runtime.ts";
import {
  startAgentEventStream,
  type AgentEventStreamStatus,
  type StopAgentEventStream,
} from "./agent/eventStreamClient.ts";
import {startPositionWsClient} from "./agent/positionWsClient.ts";
import { AgentRestClient } from "./agent/restClient.ts";
import { isUiMockMode } from "./mocks/mockConfig.ts";
import { MockAgentRestClient } from "./mocks/mockAgentRestClient.ts";
import { startMockPositionSource } from "./mocks/mockPositionSource.ts";
import { pushPosition } from "./ipc/pushPosition.ts";
import { pushStatePatch } from "./ipc/pushStatePatch.ts";
import { applyMiningEvent, replaceMiningClaims, replaceMiningDrops } from "./mining/miningDropsState.ts";
import { applyMiningLootEvent } from "./mining/miningLootState.ts";
import { applyRunEvent, replaceActiveRun, replaceRunSegments } from "./runs/runSegmentsState.ts";
import type { PositionSourceOptions, PositionSourceStatus, StopPositionSource } from "./agent/positionSource.ts";

const __dirname = path.dirname(fileURLToPath(import.meta.url))

process.env.APP_ROOT = path.join(__dirname, '..')

export const VITE_DEV_SERVER_URL = process.env['VITE_DEV_SERVER_URL']
export const MAIN_DIST = path.join(process.env.APP_ROOT, 'dist-electron')
export const RENDERER_DIST = path.join(process.env.APP_ROOT, 'dist')
export const preloadPath = path.join(MAIN_DIST, 'preload.mjs')
process.env.VITE_PUBLIC = VITE_DEV_SERVER_URL ? path.join(process.env.APP_ROOT, 'public') : RENDERER_DIST

const BACKEND_URL = process.env.ZML_BACKEND_URL ?? "http://127.0.0.1:17171";
const UI_MOCKS_ENABLED = isUiMockMode();
const agentRestClient = UI_MOCKS_ENABLED
  ? new MockAgentRestClient()
  : new AgentRestClient({ baseUrl: BACKEND_URL });

let mainWin: BrowserWindow | null = null;
let mapWin: BrowserWindow | null = null;
let overlayWin: BrowserWindow | null = null;
let stopPositionStream: StopPositionSource | null = null;
let stopEventStream: StopAgentEventStream | null = null;
let appIsQuitting = false;

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

  stopPositionStream =
    UI_MOCKS_ENABLED
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
    const [miningClaims, miningDrops] = await Promise.all([
      agentRestClient.listMiningClaims({ active: true, activeRun: true }),
      agentRestClient.listMiningDrops({ activeRun: true }),
    ]);
    replaceMiningClaims(miningClaims);
    replaceMiningDrops(miningDrops);
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
      agentRestClient.getActiveRun(),
      agentRestClient.listRuns(),
    ]);
    const runSegments = activeRun === null
      ? []
      : await agentRestClient.listActiveRunSegments();
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
      agentRestClient.listMiningTools(),
      agentRestClient.getActiveMiningTools(),
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

function updateWindowVisibilityState(): void {
  runtime.mapWindowVisible = Boolean(mapWin && !mapWin.isDestroyed() && mapWin.isVisible());
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
  registerIpc({ agentRestClient, toggleMapWindow, toggleOverlayWindow });

  // Windows
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


  // backend connector (single source of truth)
  startPositionStream();
  startEventStream();
  void refreshRunSnapshot();
  void refreshMiningToolSnapshot();
}

app.on("before-quit", () => {
  appIsQuitting = true;
  stopPositionStreamIfRunning();
});

// Quit when all windows are closed, except on macOS. There, it's common
// for applications and their menu bar to stay active until the user quits
// explicitly with Cmd + Q.
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
    mainWin = null
    mapWin = null
    overlayWin = null
  }
})

app.on('activate', () => {
  // On OS X it's common to re-create a window in the app when the
  // dock icon is clicked and there are no other windows open.
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindows()
  }
})

app.whenReady().then(createWindows)
