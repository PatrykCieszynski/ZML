import { BrowserWindow } from "electron";
import { trackWindowBounds, withSavedWindowBounds } from "./windowState.ts";

export function createMapWindow(preloadPath: string): BrowserWindow {
    const win = new BrowserWindow(withSavedWindowBounds("map", {
        width: 900,
        height: 560,
        title: "Z Mining Log - Map",
        frame: false,
        autoHideMenuBar: true,
        backgroundColor: "#000000",
        alwaysOnTop: true,
        webPreferences: {
            preload: preloadPath,
            contextIsolation: true,
            nodeIntegration: false,
        },
    }));
    trackWindowBounds("map", win);
    return win;
}
