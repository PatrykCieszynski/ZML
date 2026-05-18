import { BrowserWindow } from "electron";
import type { WindowType } from "@zml/shared";
import { getAllWindows, getWindow } from "./registry.ts";

export function getWindowsByType(type?: WindowType): BrowserWindow[] {
    if (!type) return getAllWindows();
    const win = getWindow(type);
    return win ? [win] : [];
}

export function broadcastTo(type: WindowType | undefined, channel: string, payload: unknown) {
    for (const win of getWindowsByType(type)) {
        if (!win.isDestroyed()) win.webContents.send(channel, payload);
    }
}
