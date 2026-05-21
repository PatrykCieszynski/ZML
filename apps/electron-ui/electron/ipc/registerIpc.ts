import { ipcMain } from "electron";
import {
    IPC_CMD,
    IPC_VERSION,
    assertWindowType,
    isCreateMiningToolProfileRequest,
    isSetActiveMiningToolsRequest,
    isStartRunRequest,
    isStopRunRequest,
    type BootstrapState,
    type GetBootstrapStateReq,
} from "@zml/shared";
import { runtime } from "../runtime";
import type { AgentClient } from "../agent/restClient.ts";
import { pushStatePatch } from "./pushStatePatch.ts";

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
            miningTools: runtime.miningTools,
            activeMiningTools: runtime.activeMiningTools,
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

    ipcMain.handle(IPC_CMD.LIST_MINING_TOOLS, async () => {
        const miningTools = await agentRestClient.listMiningTools();
        runtime.miningTools = miningTools;
        pushStatePatch({ miningTools });
        return miningTools;
    });

    ipcMain.handle(IPC_CMD.CREATE_MINING_TOOL, async (_evt, req: unknown) => {
        if (!isCreateMiningToolProfileRequest(req)) {
            throw new Error("Invalid create mining tool request");
        }
        const profile = await agentRestClient.createMiningTool(req);
        runtime.miningTools = await agentRestClient.listMiningTools();
        pushStatePatch({ miningTools: runtime.miningTools });
        return profile;
    });

    ipcMain.handle(IPC_CMD.DELETE_MINING_TOOL, async (_evt, toolId: unknown) => {
        if (typeof toolId !== "string" || toolId.trim() === "") {
            throw new Error("Invalid delete mining tool request");
        }
        await agentRestClient.deleteMiningTool(toolId);
        const [miningTools, activeMiningTools] = await Promise.all([
            agentRestClient.listMiningTools(),
            agentRestClient.getActiveMiningTools(),
        ]);
        runtime.miningTools = miningTools;
        runtime.activeMiningTools = activeMiningTools;
        pushStatePatch({ miningTools, activeMiningTools });
    });

    ipcMain.handle(IPC_CMD.GET_ACTIVE_MINING_TOOLS, async () => {
        const activeMiningTools = await agentRestClient.getActiveMiningTools();
        runtime.activeMiningTools = activeMiningTools;
        pushStatePatch({ activeMiningTools });
        return activeMiningTools;
    });

    ipcMain.handle(IPC_CMD.SET_ACTIVE_MINING_TOOLS, async (_evt, req: unknown) => {
        if (!isSetActiveMiningToolsRequest(req)) {
            throw new Error("Invalid set active mining tools request");
        }
        const activeMiningTools = await agentRestClient.setActiveMiningTools(req);
        runtime.activeMiningTools = activeMiningTools;
        pushStatePatch({ activeMiningTools });
        return activeMiningTools;
    });
}
