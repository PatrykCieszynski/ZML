import { clipboard, ipcMain } from "electron";
import {
    IPC_CMD,
    IPC_VERSION,
    assertWindowType,
    isCreateMiningToolProfileRequest,
    isMoveRunSegmentRequest,
    isSetActiveMiningToolsRequest,
    isSplitRunSegmentRequest,
    isStartRunRequest,
    isStopRunRequest,
    isUpdateRunRequest,
    isUpdateRunSegmentSetupRequest,
    type BootstrapState,
    type GetBootstrapStateReq,
} from "@desktop/shared";
import { runtime } from "../runtime";
import type { BackendClient } from "../backend/restClient.ts";
import type { CloudConnectionService } from "../cloud/cloudConnectionService.ts";
import { pushStatePatch } from "./pushStatePatch.ts";
import { replaceMiningClaims, replaceMiningDrops } from "../mining/miningDropsState.ts";
import { replaceMiningLoot, replaceMiningLootTotals } from "../mining/miningLootState.ts";
import { replaceActiveRun, replaceRunSegments } from "../runs/runSegmentsState.ts";

type RegisterIpcDeps = {
    backendRestClient: BackendClient;
    toggleMapWindow: () => Promise<boolean>;
    toggleOverlayWindow: () => Promise<boolean>;
    cloudConnectionService: CloudConnectionService;
};

let registered = false;

export function registerIpc({
    backendRestClient,
    toggleMapWindow,
    toggleOverlayWindow,
    cloudConnectionService,
}: RegisterIpcDeps): void {
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
            cloud: runtime.cloud,
            position: runtime.lastPosition,
            mapWindowVisible: runtime.mapWindowVisible,
            overlayWindowVisible: runtime.overlayWindowVisible,
            activeRun: runtime.activeRun,
            runs: runtime.runs,
            runSegments: runtime.runSegments,
            miningClaims: runtime.miningClaims,
            miningDrops: runtime.miningDrops,
            miningLoot: runtime.miningLoot,
            miningLootTotals: runtime.miningLootTotals,
            miningTools: runtime.miningTools,
            activeMiningTools: runtime.activeMiningTools,
        };

        return state;
    });

    ipcMain.handle(IPC_CMD.GET_AGENT_HEALTH, () => backendRestClient.getHealth());

    ipcMain.handle(IPC_CMD.COPY_TEXT, (_evt, text: unknown) => {
        if (typeof text !== "string") {
            throw new Error("Invalid copy text request");
        }
        clipboard.writeText(text);
    });

    ipcMain.handle(IPC_CMD.GET_ACTIVE_RUN, async () => {
        const activeRun = await backendRestClient.getActiveRun();
        if (activeRun === null) {
            runtime.activeRun = null;
            runtime.runSegments = [];
            replaceMiningClaims([]);
            replaceMiningDrops([]);
            replaceMiningLoot([]);
            replaceMiningLootTotals([]);
            pushStatePatch({ activeRun: null, runSegments: [] });
            return activeRun;
        }
        replaceActiveRun(activeRun);
        replaceMiningClaims(await backendRestClient.listMiningClaims({ active: false, runId: activeRun.runId }));
        replaceMiningDrops(await backendRestClient.listMiningDrops({ runId: activeRun.runId }));
        replaceMiningLoot(await backendRestClient.listMiningLoot({ runId: activeRun.runId }));
        replaceMiningLootTotals(await backendRestClient.listMiningLootTotals({ runId: activeRun.runId }));
        return activeRun;
    });

    ipcMain.handle(IPC_CMD.LIST_RUNS, async () => {
        const runs = await backendRestClient.listRuns();
        runtime.runs = runs;
        pushStatePatch({ runs });
        return runs;
    });

    ipcMain.handle(IPC_CMD.RESUME_RUN, async (_evt, runId: unknown) => {
        if (typeof runId !== "number" || !Number.isFinite(runId)) {
            throw new Error("Invalid resume run request");
        }
        const activeRun = await backendRestClient.resumeRun(runId);
        const [runs, runSegments, miningClaims, miningDrops, miningLoot, miningLootTotals] = await Promise.all([
            backendRestClient.listRuns(),
            backendRestClient.listActiveRunSegments(),
            backendRestClient.listMiningClaims({ active: false, runId }),
            backendRestClient.listMiningDrops({ runId }),
            backendRestClient.listMiningLoot({ runId }),
            backendRestClient.listMiningLootTotals({ runId }),
        ]);
        runtime.activeRun = activeRun;
        runtime.runs = runs;
        runtime.runSegments = runSegments;
        runtime.miningClaims = miningClaims;
        runtime.miningDrops = miningDrops;
        runtime.miningLoot = miningLoot;
        runtime.miningLootTotals = miningLootTotals;
        pushStatePatch({
            activeRun,
            runs,
            runSegments,
            miningClaims,
            miningDrops,
            miningLoot,
            miningLootTotals,
        });
        return activeRun;
    });

    ipcMain.handle(IPC_CMD.UPDATE_RUN, async (_evt, runId: unknown, req: unknown) => {
        if (typeof runId !== "number" || !Number.isFinite(runId) || !isUpdateRunRequest(req)) {
            throw new Error("Invalid update run request");
        }
        const activeRun = await backendRestClient.updateRun(runId, req);
        const runs = await backendRestClient.listRuns();
        runtime.runs = runs;
        if (runtime.activeRun?.runId === runId) {
            runtime.activeRun = activeRun;
            pushStatePatch({ activeRun, runs });
        } else {
            pushStatePatch({ runs });
        }
        return activeRun;
    });

    ipcMain.handle(IPC_CMD.DELETE_RUN, async (_evt, runId: unknown) => {
        if (typeof runId !== "number" || !Number.isFinite(runId)) {
            throw new Error("Invalid delete run request");
        }
        const wasActive = runtime.activeRun?.runId === runId;
        const deletedRun = await backendRestClient.deleteRun(runId);
        const runs = await backendRestClient.listRuns();
        runtime.runs = runs;

        if (wasActive) {
            runtime.activeRun = null;
            runtime.runSegments = [];
            runtime.miningClaims = [];
            runtime.miningDrops = [];
            runtime.miningLoot = [];
            runtime.miningLootTotals = [];
            pushStatePatch({
                activeRun: null,
                runs,
                runSegments: [],
                miningClaims: [],
                miningDrops: [],
                miningLoot: [],
                miningLootTotals: [],
            });
        } else {
            pushStatePatch({ runs });
        }
        return deletedRun;
    });

    ipcMain.handle(IPC_CMD.LIST_ACTIVE_RUN_SEGMENTS, async () => {
        const runSegments = await backendRestClient.listActiveRunSegments();
        replaceRunSegments(runSegments);
        return runSegments;
    });

    ipcMain.handle(IPC_CMD.LIST_RUN_SEGMENTS, async (_evt, runId: unknown) => {
        if (typeof runId !== "number" || !Number.isFinite(runId)) {
            throw new Error("Invalid list run segments request");
        }
        return backendRestClient.listRunSegments(runId);
    });

    ipcMain.handle(
        IPC_CMD.UPDATE_RUN_SEGMENT_SETUP,
        async (_evt, runId: unknown, segmentId: unknown, req: unknown) => {
            if (
                typeof runId !== "number" ||
                !Number.isFinite(runId) ||
                typeof segmentId !== "string" ||
                segmentId.trim() === "" ||
                !isUpdateRunSegmentSetupRequest(req)
            ) {
                throw new Error("Invalid update run segment setup request");
            }
            const result = await backendRestClient.updateRunSegmentSetup(runId, segmentId, req);
            await refreshActiveRunMiningState(backendRestClient);
            return result;
        },
    );

    ipcMain.handle(
        IPC_CMD.SPLIT_RUN_SEGMENT,
        async (_evt, runId: unknown, segmentId: unknown, req: unknown) => {
            if (
                typeof runId !== "number" ||
                !Number.isFinite(runId) ||
                typeof segmentId !== "string" ||
                segmentId.trim() === "" ||
                !isSplitRunSegmentRequest(req)
            ) {
                throw new Error("Invalid split run segment request");
            }
            const result = await backendRestClient.splitRunSegment(runId, segmentId, req);
            await refreshActiveRunMiningState(backendRestClient);
            return result;
        },
    );

    ipcMain.handle(
        IPC_CMD.MOVE_RUN_SEGMENT,
        async (_evt, runId: unknown, segmentId: unknown, req: unknown) => {
            if (
                typeof runId !== "number" ||
                !Number.isFinite(runId) ||
                typeof segmentId !== "string" ||
                segmentId.trim() === "" ||
                !isMoveRunSegmentRequest(req)
            ) {
                throw new Error("Invalid move run segment request");
            }
            const result = await backendRestClient.moveRunSegment(runId, segmentId, req);
            await refreshActiveRunMiningState(backendRestClient);
            return result;
        },
    );

    ipcMain.handle(IPC_CMD.TOGGLE_MAP_WINDOW, async () => toggleMapWindow());

    ipcMain.handle(IPC_CMD.TOGGLE_OVERLAY_WINDOW, async () => toggleOverlayWindow());

    ipcMain.handle(IPC_CMD.START_RUN, async (_evt, req: unknown) => {
        if (!isStartRunRequest(req)) {
            throw new Error("Invalid start run request");
        }
        const activeRun = await backendRestClient.startRun(req);
        const runs = await backendRestClient.listRuns();
        runtime.activeRun = activeRun;
        runtime.runs = runs;
        runtime.runSegments = [];
        runtime.miningClaims = [];
        runtime.miningDrops = [];
        runtime.miningLoot = [];
        runtime.miningLootTotals = [];
        pushStatePatch({
            activeRun,
            runs,
            runSegments: [],
            miningClaims: [],
            miningDrops: [],
            miningLoot: [],
            miningLootTotals: [],
        });
        return activeRun;
    });

    ipcMain.handle(IPC_CMD.STOP_RUN, async (_evt, req: unknown) => {
        if (!isStopRunRequest(req)) {
            throw new Error("Invalid stop run request");
        }
        const stoppedRun = await backendRestClient.stopRun(req);
        const runs = await backendRestClient.listRuns();
        runtime.activeRun = null;
        runtime.runs = runs;
        runtime.runSegments = [];
        runtime.miningClaims = [];
        runtime.miningDrops = [];
        runtime.miningLoot = [];
        runtime.miningLootTotals = [];
        pushStatePatch({
            activeRun: null,
            runs,
            runSegments: [],
            miningClaims: [],
            miningDrops: [],
            miningLoot: [],
            miningLootTotals: [],
        });
        return stoppedRun;
    });

    ipcMain.handle(IPC_CMD.IGNORE_MINING_CLAIM, async (_evt, claimId: unknown) => {
        if (typeof claimId !== "string" || claimId.trim() === "") {
            throw new Error("Invalid ignore mining claim request");
        }
        const claim = await backendRestClient.ignoreMiningClaim(claimId);
        runtime.miningClaims = runtime.miningClaims.map((item) =>
            item.claimId === claim.claimId ? claim : item,
        );
        pushStatePatch({ miningClaims: runtime.miningClaims });
        return claim;
    });

    ipcMain.handle(IPC_CMD.MARK_MINING_CLAIM_DEPLETED, async (_evt, claimId: unknown) => {
        if (typeof claimId !== "string" || claimId.trim() === "") {
            throw new Error("Invalid mark mining claim depleted request");
        }
        const claim = await backendRestClient.markMiningClaimDepleted(claimId);
        runtime.miningClaims = runtime.miningClaims.map((item) =>
            item.claimId === claim.claimId ? claim : item,
        );
        pushStatePatch({ miningClaims: runtime.miningClaims });
        return claim;
    });

    ipcMain.handle(IPC_CMD.LIST_MINING_TOOLS, async () => {
        const miningTools = await backendRestClient.listMiningTools();
        runtime.miningTools = miningTools;
        pushStatePatch({ miningTools });
        return miningTools;
    });

    ipcMain.handle(IPC_CMD.CREATE_MINING_TOOL, async (_evt, req: unknown) => {
        if (!isCreateMiningToolProfileRequest(req)) {
            throw new Error("Invalid create mining tool request");
        }
        const profile = await backendRestClient.createMiningTool(req);
        runtime.miningTools = await backendRestClient.listMiningTools();
        pushStatePatch({ miningTools: runtime.miningTools });
        return profile;
    });

    ipcMain.handle(IPC_CMD.DELETE_MINING_TOOL, async (_evt, toolId: unknown) => {
        if (typeof toolId !== "string" || toolId.trim() === "") {
            throw new Error("Invalid delete mining tool request");
        }
        await backendRestClient.deleteMiningTool(toolId);
        const [miningTools, activeMiningTools] = await Promise.all([
            backendRestClient.listMiningTools(),
            backendRestClient.getActiveMiningTools(),
        ]);
        runtime.miningTools = miningTools;
        runtime.activeMiningTools = activeMiningTools;
        pushStatePatch({ miningTools, activeMiningTools });
    });

    ipcMain.handle(IPC_CMD.GET_ACTIVE_MINING_TOOLS, async () => {
        const activeMiningTools = await backendRestClient.getActiveMiningTools();
        runtime.activeMiningTools = activeMiningTools;
        pushStatePatch({ activeMiningTools });
        return activeMiningTools;
    });

    ipcMain.handle(IPC_CMD.SET_ACTIVE_MINING_TOOLS, async (_evt, req: unknown) => {
        if (!isSetActiveMiningToolsRequest(req)) {
            throw new Error("Invalid set active mining tools request");
        }
        const activeMiningTools = await backendRestClient.setActiveMiningTools(req);
        runtime.activeMiningTools = activeMiningTools;
        pushStatePatch({ activeMiningTools });
        return activeMiningTools;
    });

    ipcMain.handle(IPC_CMD.CONNECT_CLOUD, async () => cloudConnectionService.connect());
    ipcMain.handle(IPC_CMD.DISCONNECT_CLOUD, async () => cloudConnectionService.disconnect());
}

async function refreshActiveRunMiningState(backendRestClient: BackendClient): Promise<void> {
    const [activeRun, runs] = await Promise.all([
        backendRestClient.getActiveRun(),
        backendRestClient.listRuns(),
    ]);
    runtime.runs = runs;

    if (activeRun === null) {
        runtime.activeRun = null;
        runtime.runSegments = [];
        runtime.miningClaims = [];
        runtime.miningDrops = [];
        runtime.miningLoot = [];
        runtime.miningLootTotals = [];
        pushStatePatch({
            activeRun: null,
            runs,
            runSegments: [],
            miningClaims: [],
            miningDrops: [],
            miningLoot: [],
            miningLootTotals: [],
        });
        return;
    }

    const runId = activeRun.runId;
    const [runSegments, miningClaims, miningDrops, miningLoot, miningLootTotals] = await Promise.all([
        backendRestClient.listRunSegments(runId),
        backendRestClient.listMiningClaims({ active: false, runId }),
        backendRestClient.listMiningDrops({ runId }),
        backendRestClient.listMiningLoot({ runId }),
        backendRestClient.listMiningLootTotals({ runId }),
    ]);
    runtime.activeRun = activeRun;
    runtime.runSegments = runSegments;
    runtime.miningClaims = miningClaims;
    runtime.miningDrops = miningDrops;
    runtime.miningLoot = miningLoot;
    runtime.miningLootTotals = miningLootTotals;
    pushStatePatch({
        activeRun,
        runs,
        runSegments,
        miningClaims,
        miningDrops,
        miningLoot,
        miningLootTotals,
    });
}
