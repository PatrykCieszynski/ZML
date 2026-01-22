import { BrowserWindow } from "electron";
import {RENDERER_DIST, VITE_DEV_SERVER_URL} from "../main.ts";
import path from "node:path";

export function createMapWindow(preloadPath: string): BrowserWindow {
    const win = new BrowserWindow({
        width: 900,
        height: 560,
        title: "ZML — Map",
        // frame: false,
        autoHideMenuBar: true,
        backgroundColor: "#000000",
        alwaysOnTop: true,
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
