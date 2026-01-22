import { BrowserWindow } from "electron";
import type { WindowType } from "@zml/shared";

export function getWindowsByType(type?: WindowType): BrowserWindow[] {
    const wins = BrowserWindow.getAllWindows();
    if (!type) return wins;

    return wins;
}

export function broadcastTo(type: WindowType | undefined, channel: string, payload: unknown) {
    for (const win of getWindowsByType(type)) {
        if (!win.isDestroyed()) win.webContents.send(channel, payload);
    }
}