import { app, type BrowserWindow, type BrowserWindowConstructorOptions, type Rectangle } from "electron";
import fs from "node:fs";
import path from "node:path";
import type { WindowType } from "@desktop/shared";

type WindowBoundsState = Partial<Record<WindowType, Rectangle>>;

const FILE_NAME = "window-state.json";

export function withSavedWindowBounds(
    type: WindowType,
    options: BrowserWindowConstructorOptions,
): BrowserWindowConstructorOptions {
    const saved = readState()[type];
    if (!saved) return options;
    return {
        ...options,
        x: saved.x,
        y: saved.y,
        width: saved.width,
        height: saved.height,
    };
}

export function trackWindowBounds(type: WindowType, win: BrowserWindow): void {
    let timer: NodeJS.Timeout | null = null;

    const flush = () => {
        if (timer) {
            clearTimeout(timer);
            timer = null;
        }
        if (win.isDestroyed() || win.isMinimized()) return;
        const next = readState();
        next[type] = win.getBounds();
        writeState(next);
    };

    const schedule = () => {
        if (timer) clearTimeout(timer);
        timer = setTimeout(flush, 500);
    };

    win.on("resize", schedule);
    win.on("move", schedule);
    win.on("close", flush);
}

function readState(): WindowBoundsState {
    try {
        const raw = fs.readFileSync(getWindowStatePath(), "utf-8");
        const parsed = JSON.parse(raw) as unknown;
        if (!isRecord(parsed)) return {};
        return parsed as WindowBoundsState;
    } catch {
        return {};
    }
}

function writeState(state: WindowBoundsState): void {
    try {
        fs.mkdirSync(path.dirname(getWindowStatePath()), { recursive: true });
        fs.writeFileSync(getWindowStatePath(), JSON.stringify(state, null, 2), "utf-8");
    } catch {
        // Window placement is QoL only; failing to persist it should not break the app.
    }
}

function getWindowStatePath(): string {
    return path.join(app.getPath("userData"), FILE_NAME);
}

function isRecord(value: unknown): value is Record<string, unknown> {
    return typeof value === "object" && value !== null;
}
