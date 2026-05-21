import { ipcMain } from "electron";
import {
    IPC_CMD,
    IPC_VERSION,
    assertWindowType,
    isStartRunRequest,
    isStopRunRequest,
    type BootstrapState,
    type GetBootstrapStateReq,
} from "@zml/shared";
import { runtime } from "../runtime";
import type { AgentClient } from "../agent/restClient.ts";

type RegisterIpcDeps = {
    agentRestClient: AgentClient;
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
            miningClaims: runtime.miningClaims,
            miningDrops: runtime.miningDrops,
        };

        return state;
    });

    ipcMain.handle(IPC_CMD.GET_AGENT_HEALTH, () => agentRestClient.getHealth());

    ipcMain.handle(IPC_CMD.START_RUN, (_evt, req: unknown) => {
        if (!isStartRunRequest(req)) {
            throw new Error("Invalid start run request");
        }
        return agentRestClient.startRun(req);
    });

    ipcMain.handle(IPC_CMD.STOP_RUN, (_evt, req: unknown) => {
        if (!isStopRunRequest(req)) {
            throw new Error("Invalid stop run request");
        }
        return agentRestClient.stopRun(req);
    });
}
