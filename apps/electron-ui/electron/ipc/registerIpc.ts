import { ipcMain } from "electron";
import {
    IPC_CMD,
    IPC_VERSION,
    assertWindowType,
    isCreateMiningToolProfileRequest,
    isSetActiveMiningToolsRequest,
    isStartRunRequest,
    isStopRunRequest,
    isUpdateRunRequest,
    type BootstrapState,
    type GetBootstrapStateReq,
} from "@zml/shared";
import { runtime } from "../runtime";
import type { AgentClient } from "../agent/restClient.ts";
import { pushStatePatch } from "./pushStatePatch.ts";
import { replaceMiningClaims, replaceMiningDrops } from "../mining/miningDropsState.ts";
import { replaceActiveRun, replaceRunSegments } from "../runs/runSegmentsState.ts";

type RegisterIpcDeps = {
    agentRestClient: AgentClient;
    toggleMapWindow: () => Promise<boolean>;
    toggleOverlayWindow: () => Promise<boolean>;
};

let registered = false;

export function registerIpc({ agentRestClient, toggleMapWindow, toggleOverlayWindow }: RegisterIpcDeps): void {
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
            mapWindowVisible: runtime.mapWindowVisible,
            overlayWindowVisible: runtime.overlayWindowVisible,
            activeRun: runtime.activeRun,
            runs: runtime.runs,
            runSegments: runtime.runSegments,
            miningClaims: runtime.miningClaims,
            miningDrops: runtime.miningDrops,
            miningLoot: runtime.miningLoot,
            miningTools: runtime.miningTools,
            activeMiningTools: runtime.activeMiningTools,
        };

        return state;
    });

    ipcMain.handle(IPC_CMD.GET_AGENT_HEALTH, () => agentRestClient.getHealth());

    ipcMain.handle(IPC_CMD.GET_ACTIVE_RUN, async () => {
        const activeRun = await agentRestClient.getActiveRun();
        if (activeRun === null) {
            runtime.activeRun = null;
            runtime.runSegments = [];
            replaceMiningClaims([]);
            replaceMiningDrops([]);
            pushStatePatch({ activeRun: null, runSegments: [] });
            return activeRun;
        }
        replaceActiveRun(activeRun);
        replaceMiningClaims(await agentRestClient.listMiningClaims({ active: false, runId: activeRun.runId }));
        replaceMiningDrops(await agentRestClient.listMiningDrops({ runId: activeRun.runId }));
        return activeRun;
    });

    ipcMain.handle(IPC_CMD.LIST_RUNS, async () => {
        const runs = await agentRestClient.listRuns();
        runtime.runs = runs;
        pushStatePatch({ runs });
        return runs;
    });

    ipcMain.handle(IPC_CMD.RESUME_RUN, async (_evt, runId: unknown) => {
        if (typeof runId !== "number" || !Number.isFinite(runId)) {
            throw new Error("Invalid resume run request");
        }
        const activeRun = await agentRestClient.resumeRun(runId);
        const [runs, runSegments, miningClaims, miningDrops] = await Promise.all([
            agentRestClient.listRuns(),
            agentRestClient.listActiveRunSegments(),
            agentRestClient.listMiningClaims({ active: false, runId }),
            agentRestClient.listMiningDrops({ runId }),
        ]);
        runtime.activeRun = activeRun;
        runtime.runs = runs;
        runtime.runSegments = runSegments;
        runtime.miningClaims = miningClaims;
        runtime.miningDrops = miningDrops;
        pushStatePatch({ activeRun, runs, runSegments, miningClaims, miningDrops });
        return activeRun;
    });

    ipcMain.handle(IPC_CMD.UPDATE_RUN, async (_evt, runId: unknown, req: unknown) => {
        if (typeof runId !== "number" || !Number.isFinite(runId) || !isUpdateRunRequest(req)) {
            throw new Error("Invalid update run request");
        }
        const activeRun = await agentRestClient.updateRun(runId, req);
        const runs = await agentRestClient.listRuns();
        runtime.runs = runs;
        if (runtime.activeRun?.runId === runId) {
            runtime.activeRun = activeRun;
            pushStatePatch({ activeRun, runs });
        } else {
            pushStatePatch({ runs });
        }
        return activeRun;
    });

    ipcMain.handle(IPC_CMD.LIST_ACTIVE_RUN_SEGMENTS, async () => {
        const runSegments = await agentRestClient.listActiveRunSegments();
        replaceRunSegments(runSegments);
        return runSegments;
    });

    ipcMain.handle(IPC_CMD.LIST_RUN_SEGMENTS, async (_evt, runId: unknown) => {
        if (typeof runId !== "number" || !Number.isFinite(runId)) {
            throw new Error("Invalid list run segments request");
        }
        return agentRestClient.listRunSegments(runId);
    });

    ipcMain.handle(IPC_CMD.TOGGLE_MAP_WINDOW, async () => toggleMapWindow());

    ipcMain.handle(IPC_CMD.TOGGLE_OVERLAY_WINDOW, async () => toggleOverlayWindow());

    ipcMain.handle(IPC_CMD.START_RUN, async (_evt, req: unknown) => {
        if (!isStartRunRequest(req)) {
            throw new Error("Invalid start run request");
        }
        const activeRun = await agentRestClient.startRun(req);
        const runs = await agentRestClient.listRuns();
        runtime.activeRun = activeRun;
        runtime.runs = runs;
        runtime.runSegments = [];
        runtime.miningClaims = [];
        runtime.miningDrops = [];
        pushStatePatch({ activeRun, runs, runSegments: [], miningClaims: [], miningDrops: [] });
        return activeRun;
    });

    ipcMain.handle(IPC_CMD.STOP_RUN, async (_evt, req: unknown) => {
        if (!isStopRunRequest(req)) {
            throw new Error("Invalid stop run request");
        }
        const stoppedRun = await agentRestClient.stopRun(req);
        const runs = await agentRestClient.listRuns();
        runtime.activeRun = null;
        runtime.runs = runs;
        runtime.runSegments = [];
        runtime.miningClaims = [];
        runtime.miningDrops = [];
        pushStatePatch({ activeRun: null, runs, runSegments: [], miningClaims: [], miningDrops: [] });
        return stoppedRun;
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
