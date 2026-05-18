import { IPC_PUSH, type PushStatePatch, type RuntimeStatePatch } from "@zml/shared";
import { broadcastTo } from "../windows/broadcast.ts";

export function pushStatePatch(patch: RuntimeStatePatch): void {
  broadcastTo(undefined, IPC_PUSH.STATE_PATCH, { patch } satisfies PushStatePatch);
}
