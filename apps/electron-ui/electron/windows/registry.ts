import type { BrowserWindow } from "electron";
import type { WindowType } from "@zml/shared";

const windows = new Map<WindowType, BrowserWindow>();

export function registerWindow(type: WindowType, win: BrowserWindow): void {
    windows.set(type, win);

    win.on("closed", () => {
        // Avoid keeping dead references around.
        if (windows.get(type) === win) windows.delete(type);
    });
}

export function getWindow(type: WindowType): BrowserWindow | undefined {
    const w = windows.get(type);
    if (!w || w.isDestroyed()) return undefined;
    return w;
}

export function getAllWindows(): BrowserWindow[] {
    return [...windows.values()].filter((w) => !w.isDestroyed());
}
