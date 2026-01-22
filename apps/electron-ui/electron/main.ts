import { app, BrowserWindow } from 'electron'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

import { registerIpc } from "./ipc/registerIpc";
import { createMainWindow } from "./windows/createMainWindow";
import { createMapWindow } from "./windows/createMapWindow";
import { loadRenderer } from "./windows/loadRenderer";
import { registerWindow } from "./windows/registry";

import {IPC_PUSH, OcrPositionEvent, PushPosition} from "@zml/shared";
import {runtime} from "./runtime.ts";
import {broadcastTo} from "./windows/broadcast.ts";
import {startPositionWsClient} from "./agent/positionWsClient.ts";

const __dirname = path.dirname(fileURLToPath(import.meta.url))

process.env.APP_ROOT = path.join(__dirname, '..')

export const VITE_DEV_SERVER_URL = process.env['VITE_DEV_SERVER_URL']
export const MAIN_DIST = path.join(process.env.APP_ROOT, 'dist-electron')
export const RENDERER_DIST = path.join(process.env.APP_ROOT, 'dist')
export const preloadPath = path.join(MAIN_DIST, 'preload.mjs')
process.env.VITE_PUBLIC = VITE_DEV_SERVER_URL ? path.join(process.env.APP_ROOT, 'public') : RENDERER_DIST

const BACKEND_URL = process.env.ZML_BACKEND_URL ?? "http://127.0.0.1:17171";

let mainWin: BrowserWindow | null
let mapWin: BrowserWindow | null

function pushPosition(ev: OcrPositionEvent) {
  console.debug(`[main] position event: seq=${ev.seq} tsMs=${ev.tsMs} x=${ev.payload.position.x} y=${ev.payload.position.y}`);
  runtime.lastPosition = ev.payload;
  broadcastTo("map", IPC_PUSH.POSITION, { event: ev } satisfies PushPosition);
}

async function createWindows() {
  registerIpc();

  // Windows
  mainWin = createMainWindow(preloadPath);
  registerWindow("main", mainWin);
  await loadRenderer(mainWin, "main");

  mapWin = createMapWindow(preloadPath);
  registerWindow("map", mapWin);
  await loadRenderer(mapWin, "map");


  // backend connector (single source of truth)
  const agentWs = startPositionWsClient({
    baseUrl: BACKEND_URL,
    onStatus: (s, err) => {
      runtime.agent.status = s === "connected" ? "connected" : s === "connecting" ? "connecting" : "disconnected";
      runtime.agent.lastError = err || undefined;
      runtime.streams.ws = s === "connected";
    },
    onEvent: pushPosition,
  });

  app.on("before-quit", () => agentWs());

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
}

app.whenReady().then(createWindows)