import { BrowserWindow } from "electron";
import { trackWindowBounds, withSavedWindowBounds } from "./windowState.ts";

export function createOverlayWindow(preloadPath: string): BrowserWindow {
    const win = new BrowserWindow(withSavedWindowBounds("overlay", {
        width: 390,
        height: 124,
        minWidth: 320,
        minHeight: 96,
        title: "Z Mining Log - Overlay",
        frame: false,
        transparent: true,
        resizable: true,
        movable: true,
        show: false,
        skipTaskbar: true,
        alwaysOnTop: true,
        autoHideMenuBar: true,
        backgroundColor: "#00000000",
        webPreferences: {
            preload: preloadPath,
            contextIsolation: true,
            nodeIntegration: false,
        },
    }));
    win.setAlwaysOnTop(true, "screen-saver");
    trackWindowBounds("overlay", win);
    return win;
}
