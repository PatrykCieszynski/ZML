import type { BrowserWindow } from "electron";
import type { WindowType } from "@zml/shared";
import { getIndexHtml } from "./paths.ts";
import { RENDERER_DIST, VITE_DEV_SERVER_URL } from "../main.ts";

export async function loadRenderer(win: BrowserWindow, windowType: WindowType): Promise<void> {
    const params = new URLSearchParams({ windowType });
    const search = `?${params.toString()}`;

    const devUrl = VITE_DEV_SERVER_URL;
    if (devUrl) {
        await win.loadURL(`${devUrl}${search}`);
        return;
    }

    if (!RENDERER_DIST) {
        throw new Error("RENDERER_DIST is not set (did you forget to set it in main.ts?)");
    }

    const indexHtml = getIndexHtml(RENDERER_DIST);
    await win.loadFile(indexHtml, { search });
}
