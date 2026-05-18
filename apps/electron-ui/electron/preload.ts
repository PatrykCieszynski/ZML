import { contextBridge, ipcRenderer } from "electron";
import type {
  AgentHealthDto,
  BootstrapState,
  GetBootstrapStateReq,
  OcrPositionEvent,
  PushPosition,
  PushStatePatch,
  RuntimeStatePatch,
  RunDto,
  StartRunRequest,
  StopRunRequest,
  WindowType,
} from "@zml/shared";
import { IPC_CMD, IPC_PUSH } from "@zml/shared";

type Unsubscribe = () => void;

type ZmlApi = {
  getBootstrapState: (windowType: WindowType) => Promise<BootstrapState>;
  getAgentHealth: () => Promise<AgentHealthDto>;
  startRun: (request: StartRunRequest) => Promise<RunDto>;
  stopRun: (request?: StopRunRequest) => Promise<RunDto>;
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

  async startRun(request) {
    return ipcRenderer.invoke(IPC_CMD.START_RUN, request) as Promise<RunDto>;
  },

  async stopRun(request = {}) {
    return ipcRenderer.invoke(IPC_CMD.STOP_RUN, request) as Promise<RunDto>;
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
