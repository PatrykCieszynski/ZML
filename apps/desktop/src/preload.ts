import { contextBridge, ipcRenderer } from "electron";
import { IPC_CMD, IPC_PUSH } from "@zml/shared";
import type {
  BootstrapState,
  GetBootstrapStateReq,
  OcrPositionEvent,
  PushPosition,
  WindowType,
} from "@zml/shared";

type Unsubscribe = () => void;

type ZmlApi = {
  getBootstrapState: (windowType: WindowType) => Promise<BootstrapState>;
  onPosition: (cb: (event: OcrPositionEvent) => void) => Unsubscribe;
  offPosition: (cb: (event: OcrPositionEvent) => void) => void;
};

const api: ZmlApi = {
  async getBootstrapState(windowType) {
    const req: GetBootstrapStateReq = { windowType };
    return ipcRenderer.invoke(IPC_CMD.GET_BOOTSTRAP_STATE, req) as Promise<BootstrapState>;
  },

  onPosition(cb) {
    // IMPORTANT: keep the wrapper reference to allow proper removeListener
    const handler = (_evt: Electron.IpcRendererEvent, payload: PushPosition) => {
      cb(payload.event);
    };

    ipcRenderer.on(IPC_PUSH.POSITION, handler);

    // Return unsubscribe for React cleanup
    return () => {
      ipcRenderer.removeListener(IPC_PUSH.POSITION, handler);
    };
  },

  offPosition(cb) {
    // You can’t remove cb directly because we wrap it.
    // This method exists only if you implement your own callback registry.
    // For now: prefer unsubscribe returned by onPosition().
    // Keeping this method as a deliberate no-op prevents misuse.
    void cb;
  },
};

contextBridge.exposeInMainWorld("zml", api);