import { contextBridge, ipcRenderer } from "electron";
import type { BootstrapState, GetBootstrapStateReq, OcrPositionEvent, PushPosition, WindowType } from "@zml/shared";
import { IPC_CMD, IPC_PUSH } from "@zml/shared";

type Unsubscribe = () => void;

type ZmlApi = {
  getBootstrapState: (windowType: WindowType) => Promise<BootstrapState>;
  onPosition: (cb: (event: OcrPositionEvent) => void) => Unsubscribe;
};

const api: ZmlApi = {
  async getBootstrapState(windowType) {
    const req: GetBootstrapStateReq = { windowType };
    return ipcRenderer.invoke(IPC_CMD.GET_BOOTSTRAP_STATE, req) as Promise<BootstrapState>;
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
};

contextBridge.exposeInMainWorld("zml", api);