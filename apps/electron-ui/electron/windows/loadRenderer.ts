import type { BrowserWindow } from "electron";
import type { WindowType } from "@zml/shared";
import { getIndexHtml } from "./paths.ts";
import {VITE_DEV_SERVER_URL} from "../main.ts";

export async function loadRenderer(win: BrowserWindow, windowType: WindowType): Promise<void> {
    const params = new URLSearchParams({ windowType });
    const search = `?${params.toString()}`;

    const devUrl = VITE_DEV_SERVER_URL;
    if (devUrl) {
        await win.loadURL(`${devUrl}${search}`);
        return;
    }

    const distDir = VITE_DEV_SERVER_URL;
    if (!distDir) {
        throw new Error("process.env.DIST is not set (did you forget to set it in main.ts?)");
    }

    const indexHtml = getIndexHtml(distDir);
    await win.loadFile(indexHtml, { search });
}
