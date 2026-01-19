import { ipcMain } from "electron";
import { assertWindowType, IPC_CMD, IPC_VERSION } from "@zml/shared";
import type { BootstrapState, GetBootstrapStateReq } from "@zml/shared";
import { runtime } from "../appstate/state";

export function registerIpc(): void {
    ipcMain.handle(IPC_CMD.GET_BOOTSTRAP_STATE, (_evt, req: GetBootstrapStateReq) => {
        if (!req || typeof req !== "object") {
            throw new Error("Invalid GET_BOOTSTRAP_STATE request");
        }

        assertWindowType(req.windowType);

        const state: BootstrapState = {
            ipcVersion: IPC_VERSION,
            windowType: req.windowType,
            nowTsMs: Date.now(),
            agent: { status: runtime.agent.status },
            streams: { ...runtime.streams },
            position: runtime.lastPosition,
        };

        return state;
    });
}
