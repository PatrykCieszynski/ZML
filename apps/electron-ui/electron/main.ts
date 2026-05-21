import { app, BrowserWindow } from 'electron'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

import { registerIpc } from "./ipc/registerIpc";
import { createMainWindow } from "./windows/createMainWindow";
import { createMapWindow } from "./windows/createMapWindow";
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

let mainWin: BrowserWindow | null
let mapWin: BrowserWindow | null
let stopPositionStream: StopPositionSource | null = null;
let stopEventStream: StopAgentEventStream | null = null;

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
  }
}

async function refreshMiningSnapshot() {
  try {
    const [miningClaims, miningDrops] = await Promise.all([
      agentRestClient.listMiningClaims({ active: true }),
      agentRestClient.listMiningDrops({ windowMinutes: 30 }),
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
    onEvent: applyMiningEvent,
  });
}

function stopPositionStreamIfRunning() {
  stopPositionStream?.();
  stopPositionStream = null;
  stopEventStream?.();
  stopEventStream = null;
}

async function createWindows() {
  registerIpc({ agentRestClient });

  // Windows
  mainWin = createMainWindow(preloadPath);
  registerWindow("main", mainWin);
  await loadRenderer(mainWin, "main");
  if (VITE_DEV_SERVER_URL) mainWin.webContents.openDevTools({ mode: "detach" });

  mapWin = createMapWindow(preloadPath);
  registerWindow("map", mapWin);
  await loadRenderer(mapWin, "map");
  if (VITE_DEV_SERVER_URL) mapWin.webContents.openDevTools({ mode: "detach" });


  // backend connector (single source of truth)
  startPositionStream();
  startEventStream();
  void refreshMiningToolSnapshot();
}

app.on("before-quit", stopPositionStreamIfRunning);

// Quit when all windows are closed, except on macOS. There, it's common
// for applications and their menu bar to stay active until the user quits
// explicitly with Cmd + Q.
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
    mainWin = null
    mapWin = null
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
