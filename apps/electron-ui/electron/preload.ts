import { contextBridge, ipcRenderer } from "electron";
import type {
  AgentHealthDto,
  ActiveMiningToolsDto,
  BootstrapState,
  CreateMiningToolProfileRequest,
  GetBootstrapStateReq,
  MiningToolProfileDto,
  OcrPositionEvent,
  PushPosition,
  PushStatePatch,
  RuntimeStatePatch,
  RunDto,
  RunSegmentDto,
  SetActiveMiningToolsRequest,
  StartRunRequest,
  StopRunRequest,
  WindowType,
} from "@zml/shared";
import { IPC_CMD, IPC_PUSH } from "@zml/shared";

type Unsubscribe = () => void;

type ZmlApi = {
  getBootstrapState: (windowType: WindowType) => Promise<BootstrapState>;
  getAgentHealth: () => Promise<AgentHealthDto>;
  getActiveRun: () => Promise<RunDto | null>;
  listActiveRunSegments: () => Promise<RunSegmentDto[]>;
  listRunSegments: (runId: number) => Promise<RunSegmentDto[]>;
  startRun: (request: StartRunRequest) => Promise<RunDto>;
  stopRun: (request?: StopRunRequest) => Promise<RunDto>;
  listMiningTools: () => Promise<MiningToolProfileDto[]>;
  createMiningTool: (request: CreateMiningToolProfileRequest) => Promise<MiningToolProfileDto>;
  deleteMiningTool: (toolId: string) => Promise<void>;
  getActiveMiningTools: () => Promise<ActiveMiningToolsDto>;
  setActiveMiningTools: (request: SetActiveMiningToolsRequest) => Promise<ActiveMiningToolsDto>;
  onPosition: (cb: (event: OcrPositionEvent) => void) => Unsubscribe;
  onStatePatch: (cb: (patch: RuntimeStatePatch) => void) => Unsubscribe;
};

const api: ZmlApi = {
  async getBootstrapState(windowType) {
    const req: GetBootstrapStateReq = { windowType };
    return ipcRenderer.invoke(IPC_CMD.GET_BOOTSTRAP_STATE, req) as Promise<BootstrapState>;
  },

  async getAgentHealth() {
    return ipcRenderer.invoke(IPC_CMD.GET_AGENT_HEALTH) as Promise<AgentHealthDto>;
  },

  async getActiveRun() {
    return ipcRenderer.invoke(IPC_CMD.GET_ACTIVE_RUN) as Promise<RunDto | null>;
  },

  async listActiveRunSegments() {
    return ipcRenderer.invoke(IPC_CMD.LIST_ACTIVE_RUN_SEGMENTS) as Promise<RunSegmentDto[]>;
  },

  async listRunSegments(runId) {
    return ipcRenderer.invoke(IPC_CMD.LIST_RUN_SEGMENTS, runId) as Promise<RunSegmentDto[]>;
  },

  async startRun(request) {
    return ipcRenderer.invoke(IPC_CMD.START_RUN, request) as Promise<RunDto>;
  },

  async stopRun(request = {}) {
    return ipcRenderer.invoke(IPC_CMD.STOP_RUN, request) as Promise<RunDto>;
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
