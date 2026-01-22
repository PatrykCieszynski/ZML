import { app, BrowserWindow } from 'electron'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

import { registerIpc } from "./ipc/registerIpc";
import { pushPosition } from "./ipc/pushPosition";
import { createMainWindow } from "./windows/createMainWindow";
import { createMapWindow } from "./windows/createMapWindow";
import { loadRenderer } from "./windows/loadRenderer";
import { registerWindow } from "./windows/registry";

import type { OcrPositionEvent } from "@zml/shared";

const __dirname = path.dirname(fileURLToPath(import.meta.url))

process.env.APP_ROOT = path.join(__dirname, '..')

// 🚧 Use ['ENV_NAME'] avoid vite:define plugin - Vite@2.x
export const VITE_DEV_SERVER_URL = process.env['VITE_DEV_SERVER_URL']
export const MAIN_DIST = path.join(process.env.APP_ROOT, 'dist-electron')
export const RENDERER_DIST = path.join(process.env.APP_ROOT, 'dist')
export const preloadPath = path.join(MAIN_DIST, 'preload.mjs')
process.env.VITE_PUBLIC = VITE_DEV_SERVER_URL ? path.join(process.env.APP_ROOT, 'public') : RENDERER_DIST

let mainWin: BrowserWindow | null
let mapWin: BrowserWindow | null

async function createWindows() {
  registerIpc();

  mainWin = createMainWindow(preloadPath);
  registerWindow("main", mainWin);
  await loadRenderer(mainWin, "main");

  mapWin = createMapWindow(preloadPath);
  registerWindow("map", mapWin);
  await loadRenderer(mapWin, "map");

  if (!app.isPackaged) {
    startMockPositionFeed();
  }
}

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


function startMockPositionFeed(): void {
  // Dev-only: simulate incoming agent positions so you can see the map moving.
  let x = 136_000;
  let y = 76_800;

  setInterval(() => {
    x += 1;
    y += (x % 5) - 2;

    const ev: OcrPositionEvent = {
      type: "ocr.position",
      seq: Date.now(), // replace with monotonic seq later
      tsMs: Date.now(),
      payload: {
        tsMs: Date.now(),
        position: { planetName: "", x, y, z: null },
      },
    };

    pushPosition(ev);
  }, 120);
}