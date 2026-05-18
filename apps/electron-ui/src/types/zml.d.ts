import type {
  AgentHealthDto,
  BootstrapState,
  OcrPositionEvent,
  RuntimeStatePatch,
  WindowType,
} from "@zml/shared";

declare global {
  interface Window {
    zml: {
      getBootstrapState: (windowType: WindowType) => Promise<BootstrapState>;
      getAgentHealth: () => Promise<AgentHealthDto>;
      onPosition: (cb: (event: OcrPositionEvent) => void) => () => void;
      onStatePatch: (cb: (patch: RuntimeStatePatch) => void) => () => void;
    };
  }
}

export {};
