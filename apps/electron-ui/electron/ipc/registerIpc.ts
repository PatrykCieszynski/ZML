import { ipcMain } from "electron";
import { IPC_CMD, IPC_VERSION, assertWindowType, type BootstrapState, type GetBootstrapStateReq } from "@zml/shared";
import { runtime } from "../runtime";

export function registerIpc(): void {
    ipcMain.handle(IPC_CMD.GET_BOOTSTRAP_STATE, (_evt, req: GetBootstrapStateReq) => {
        assertWindowType(req.windowType);

        const state: BootstrapState = {
            ipcVersion: IPC_VERSION,
            windowType: req.windowType,
            nowTsMs: Date.now(),
            agent: runtime.agent,
            streams: runtime.streams,
            position: runtime.lastPosition,
        };

        return state;
    });
}
