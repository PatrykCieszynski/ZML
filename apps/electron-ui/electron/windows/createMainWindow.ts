import { BrowserWindow } from "electron";

export function createMainWindow(preloadPath: string): BrowserWindow {
    return new BrowserWindow({
        width: 1180,
        height: 820,
        title: "ZML — Main",
        webPreferences: {
            preload: preloadPath,
            contextIsolation: true,
            nodeIntegration: false,
        },
    });
}
