import { IPC_PUSH } from "@zml/shared";
import type { OcrPositionEvent, PushPosition } from "@zml/shared";
import { runtime } from "../appstate/state";
import { getPushTarget } from "../windows/registry";

export function pushPosition(event: OcrPositionEvent): void {
    // If your envelope differs, adjust this single line.
    runtime.lastPosition = event.payload;

    const target = getPushTarget();
    if (!target) return;

    target.webContents.send(
        IPC_PUSH.POSITION,
        { event } satisfies PushPosition
    );
}
