import { BrowserWindow } from "electron";
import path from "node:path";
import {RENDERER_DIST, VITE_DEV_SERVER_URL} from "../main.ts";


export function createMainWindow(preloadPath: string): BrowserWindow {
    const win = new BrowserWindow({
        width: 1180,
        height: 820,
        title: "ZML — Main",
        webPreferences: {
            preload: preloadPath,
            contextIsolation: true,
            nodeIntegration: false,
        },
    });

    if (VITE_DEV_SERVER_URL) {
        win.loadURL(VITE_DEV_SERVER_URL)
        win.webContents.openDevTools({ mode: "detach" });
    } else {
        // win.loadFile('dist/index.html')
        win.loadFile(path.join(RENDERER_DIST, 'index.html'))
    }

    return win;
}