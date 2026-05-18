import { ipcMain } from "electron";
import { IPC_CMD, IPC_VERSION, assertWindowType, type BootstrapState, type GetBootstrapStateReq } from "@zml/shared";
import { runtime } from "../runtime";
import type { AgentRestClient } from "../agent/restClient.ts";

type RegisterIpcDeps = {
    agentRestClient: AgentRestClient;
};

let registered = false;

export function registerIpc({ agentRestClient }: RegisterIpcDeps): void {
    if (registered) return;
    registered = true;

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

    ipcMain.handle(IPC_CMD.GET_AGENT_HEALTH, () => agentRestClient.getHealth());
}
