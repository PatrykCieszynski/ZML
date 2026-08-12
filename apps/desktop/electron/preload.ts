import { contextBridge, ipcRenderer } from "electron";
import type {
  BackendHealthDto,
  ActiveMiningToolsDto,
  BootstrapState,
  CloudConnectionState,
  CreateMiningToolProfileRequest,
  GetBootstrapStateReq,
  MiningClaimDto,
  MiningToolProfileDto,
  MoveRunSegmentRequest,
  OcrCalibrationSnapshotDto,
  OcrPositionEvent,
  OcrRecalibrationResultDto,
  PushPosition,
  PushStatePatch,
  RuntimeStatePatch,
  RunDto,
  RunSegmentDto,
  SetActiveMiningToolsRequest,
  SplitRunSegmentRequest,
  StartRunRequest,
  StopRunRequest,
  UpdateRunRequest,
  UpdateRunSegmentSetupRequest,
  WindowType,
} from "@desktop/shared";
import { IPC_CMD, IPC_PUSH } from "@desktop/shared";

type Unsubscribe = () => void;

type ZmlApi = {
  getBootstrapState: (windowType: WindowType) => Promise<BootstrapState>;
  getBackendHealth: () => Promise<BackendHealthDto>;
  getOcrCalibration: () => Promise<OcrCalibrationSnapshotDto>;
  recalibrateOcr: () => Promise<OcrRecalibrationResultDto>;
  copyText: (text: string) => Promise<void>;
  getActiveRun: () => Promise<RunDto | null>;
  listRuns: () => Promise<RunDto[]>;
  resumeRun: (runId: number) => Promise<RunDto>;
  updateRun: (runId: number, request: UpdateRunRequest) => Promise<RunDto>;
  deleteRun: (runId: number) => Promise<RunDto>;
  listActiveRunSegments: () => Promise<RunSegmentDto[]>;
  listRunSegments: (runId: number) => Promise<RunSegmentDto[]>;
  updateRunSegmentSetup: (
    runId: number,
    segmentId: string,
    request: UpdateRunSegmentSetupRequest,
  ) => Promise<RunSegmentDto>;
  splitRunSegment: (
    runId: number,
    segmentId: string,
    request: SplitRunSegmentRequest,
  ) => Promise<RunSegmentDto>;
  moveRunSegment: (
    runId: number,
    segmentId: string,
    request: MoveRunSegmentRequest,
  ) => Promise<RunSegmentDto>;
  toggleMapWindow: () => Promise<boolean>;
  toggleOverlayWindow: () => Promise<boolean>;
  startRun: (request: StartRunRequest) => Promise<RunDto>;
  stopRun: (request?: StopRunRequest) => Promise<RunDto>;
  markMiningClaimDepleted: (claimId: string) => Promise<MiningClaimDto>;
  ignoreMiningClaim: (claimId: string) => Promise<MiningClaimDto>;
  listMiningTools: () => Promise<MiningToolProfileDto[]>;
  createMiningTool: (request: CreateMiningToolProfileRequest) => Promise<MiningToolProfileDto>;
  deleteMiningTool: (toolId: string) => Promise<void>;
  getActiveMiningTools: () => Promise<ActiveMiningToolsDto>;
  setActiveMiningTools: (request: SetActiveMiningToolsRequest) => Promise<ActiveMiningToolsDto>;
  connectCloud: () => Promise<CloudConnectionState>;
  disconnectCloud: () => Promise<CloudConnectionState>;
  onPosition: (cb: (event: OcrPositionEvent) => void) => Unsubscribe;
  onStatePatch: (cb: (patch: RuntimeStatePatch) => void) => Unsubscribe;
};

const api: ZmlApi = {
  async getBootstrapState(windowType) {
    const req: GetBootstrapStateReq = { windowType };
    return ipcRenderer.invoke(IPC_CMD.GET_BOOTSTRAP_STATE, req) as Promise<BootstrapState>;
  },

  async getBackendHealth() {
    return ipcRenderer.invoke(IPC_CMD.GET_AGENT_HEALTH) as Promise<BackendHealthDto>;
  },

  async getOcrCalibration() {
    return ipcRenderer.invoke(IPC_CMD.GET_OCR_CALIBRATION) as Promise<OcrCalibrationSnapshotDto>;
  },

  async recalibrateOcr() {
    return ipcRenderer.invoke(IPC_CMD.RECALIBRATE_OCR) as Promise<OcrRecalibrationResultDto>;
  },

  async copyText(text) {
    return ipcRenderer.invoke(IPC_CMD.COPY_TEXT, text) as Promise<void>;
  },

  async getActiveRun() {
    return ipcRenderer.invoke(IPC_CMD.GET_ACTIVE_RUN) as Promise<RunDto | null>;
  },

  async listRuns() {
    return ipcRenderer.invoke(IPC_CMD.LIST_RUNS) as Promise<RunDto[]>;
  },

  async resumeRun(runId) {
    return ipcRenderer.invoke(IPC_CMD.RESUME_RUN, runId) as Promise<RunDto>;
  },

  async updateRun(runId, request) {
    return ipcRenderer.invoke(IPC_CMD.UPDATE_RUN, runId, request) as Promise<RunDto>;
  },

  async deleteRun(runId) {
    return ipcRenderer.invoke(IPC_CMD.DELETE_RUN, runId) as Promise<RunDto>;
  },

  async listActiveRunSegments() {
    return ipcRenderer.invoke(IPC_CMD.LIST_ACTIVE_RUN_SEGMENTS) as Promise<RunSegmentDto[]>;
  },

  async listRunSegments(runId) {
    return ipcRenderer.invoke(IPC_CMD.LIST_RUN_SEGMENTS, runId) as Promise<RunSegmentDto[]>;
  },

  async updateRunSegmentSetup(runId, segmentId, request) {
    return ipcRenderer.invoke(
      IPC_CMD.UPDATE_RUN_SEGMENT_SETUP,
      runId,
      segmentId,
      request,
    ) as Promise<RunSegmentDto>;
  },

  async splitRunSegment(runId, segmentId, request) {
    return ipcRenderer.invoke(
      IPC_CMD.SPLIT_RUN_SEGMENT,
      runId,
      segmentId,
      request,
    ) as Promise<RunSegmentDto>;
  },

  async moveRunSegment(runId, segmentId, request) {
    return ipcRenderer.invoke(
      IPC_CMD.MOVE_RUN_SEGMENT,
      runId,
      segmentId,
      request,
    ) as Promise<RunSegmentDto>;
  },

  async toggleMapWindow() {
    return ipcRenderer.invoke(IPC_CMD.TOGGLE_MAP_WINDOW) as Promise<boolean>;
  },

  async toggleOverlayWindow() {
    return ipcRenderer.invoke(IPC_CMD.TOGGLE_OVERLAY_WINDOW) as Promise<boolean>;
  },

  async startRun(request) {
    return ipcRenderer.invoke(IPC_CMD.START_RUN, request) as Promise<RunDto>;
  },

  async stopRun(request = {}) {
    return ipcRenderer.invoke(IPC_CMD.STOP_RUN, request) as Promise<RunDto>;
  },

  async ignoreMiningClaim(claimId) {
    return ipcRenderer.invoke(IPC_CMD.IGNORE_MINING_CLAIM, claimId) as Promise<MiningClaimDto>;
  },

  async markMiningClaimDepleted(claimId) {
    return ipcRenderer.invoke(IPC_CMD.MARK_MINING_CLAIM_DEPLETED, claimId) as Promise<MiningClaimDto>;
  },

  async listMiningTools() {
    return ipcRenderer.invoke(IPC_CMD.LIST_MINING_TOOLS) as Promise<MiningToolProfileDto[]>;
  },

  async createMiningTool(request) {
    return ipcRenderer.invoke(IPC_CMD.CREATE_MINING_TOOL, request) as Promise<MiningToolProfileDto>;
  },

  async deleteMiningTool(toolId) {
    return ipcRenderer.invoke(IPC_CMD.DELETE_MINING_TOOL, toolId) as Promise<void>;
  },

  async getActiveMiningTools() {
    return ipcRenderer.invoke(IPC_CMD.GET_ACTIVE_MINING_TOOLS) as Promise<ActiveMiningToolsDto>;
  },

  async setActiveMiningTools(request) {
    return ipcRenderer.invoke(IPC_CMD.SET_ACTIVE_MINING_TOOLS, request) as Promise<ActiveMiningToolsDto>;
  },

  async connectCloud() {
    return ipcRenderer.invoke(IPC_CMD.CONNECT_CLOUD) as Promise<CloudConnectionState>;
  },

  async disconnectCloud() {
    return ipcRenderer.invoke(IPC_CMD.DISCONNECT_CLOUD) as Promise<CloudConnectionState>;
  },

  onPosition(cb) {
    const handler = (_evt: Electron.IpcRendererEvent, payload: PushPosition) => {
      cb(payload.event);
    };

    ipcRenderer.on(IPC_PUSH.POSITION, handler);

    return () => {
      ipcRenderer.removeListener(IPC_PUSH.POSITION, handler);
    };
  },

  onStatePatch(cb) {
    const handler = (_evt: Electron.IpcRendererEvent, payload: PushStatePatch) => {
      cb(payload.patch);
    };

    ipcRenderer.on(IPC_PUSH.STATE_PATCH, handler);

    return () => {
      ipcRenderer.removeListener(IPC_PUSH.STATE_PATCH, handler);
    };
  },
};

contextBridge.exposeInMainWorld("zml", api);
