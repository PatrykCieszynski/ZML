import { IPC_PUSH, type OcrPositionEvent, type PushPosition } from "@zml/shared";
import { runtime } from "../runtime";
import { getWindow } from "../windows/registry";

/**
 * Main -> Renderer push. Keep it as a single function to avoid
 * "send from random places" chaos later.
 */
export function pushPosition(event: OcrPositionEvent): void {
  runtime.lastPosition = event.payload;

  // For now: map + hud are consumers.
  const targets = [getWindow("map"), getWindow("hud"), getWindow("main")].filter(Boolean);
  for (const w of targets) {
    w!.webContents.send(IPC_PUSH.POSITION, { event } satisfies PushPosition);
  }
}
