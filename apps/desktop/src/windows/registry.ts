import type { BrowserWindow } from "electron";
import type { WindowType } from "@zml/shared";

const windows = new Map<WindowType, BrowserWindow>();

export function registerWindow(type: WindowType, win: BrowserWindow): void {
    windows.set(type, win);

    win.on("closed", () => {
        const cur = windows.get(type);
        if (cur === win) windows.delete(type);
    });
}

export function getWindow(type: WindowType): BrowserWindow | null {
    const win = windows.get(type);
    if (!win || win.isDestroyed()) return null;
    return win;
}

// MVP routing: map if exists else main
export function getPushTarget(): BrowserWindow | null {
    return getWindow("map") ?? getWindow("main") ?? null;
}