import { BrowserWindow } from "electron";
import { trackWindowBounds, withSavedWindowBounds } from "./windowState.ts";

export function createMainWindow(preloadPath: string): BrowserWindow {
    const win = new BrowserWindow(withSavedWindowBounds("main", {
        width: 1180,
        height: 820,
        title: "Z Mining Log - Main",
        webPreferences: {
            preload: preloadPath,
            contextIsolation: true,
            nodeIntegration: false,
        },
    }));
    trackWindowBounds("main", win);
    return win;
}
