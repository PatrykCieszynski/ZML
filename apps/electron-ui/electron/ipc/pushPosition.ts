import { IPC_PUSH, type OcrPositionEvent, type PushPosition } from "@zml/shared";
import { runtime } from "../runtime";
import { getWindow } from "../windows/registry";
import type { BrowserWindow } from "electron";

function isWindow(win: BrowserWindow | undefined): win is BrowserWindow {
  return win !== undefined;
}

/**
 * Main -> Renderer push. Keep it as a single function to avoid
 * "send from random places" chaos later.
 */
export function pushPosition(event: OcrPositionEvent): void {
  runtime.lastPosition = event.payload;

  // Keep the high-rate position stream away from diagnostics-heavy windows.
  const targets = [getWindow("map"), getWindow("hud")].filter(isWindow);
  for (const w of targets) {
    w.webContents.send(IPC_PUSH.POSITION, { event } satisfies PushPosition);
  }
}
