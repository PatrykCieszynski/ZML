import { BrowserWindow } from "electron";

export function createMapWindow(preloadPath: string): BrowserWindow {
    return new BrowserWindow({
        width: 900,
        height: 560,
        title: "Z Mining Log - Map",
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
}
