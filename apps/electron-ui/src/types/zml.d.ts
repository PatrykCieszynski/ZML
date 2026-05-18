import type {
  AgentHealthDto,
  BootstrapState,
  OcrPositionEvent,
  RuntimeStatePatch,
  RunDto,
  StartRunRequest,
  StopRunRequest,
  WindowType,
} from "@zml/shared";

declare global {
  interface Window {
    zml: {
      getBootstrapState: (windowType: WindowType) => Promise<BootstrapState>;
      getAgentHealth: () => Promise<AgentHealthDto>;
      startRun: (request: StartRunRequest) => Promise<RunDto>;
      stopRun: (request?: StopRunRequest) => Promise<RunDto>;
      onPosition: (cb: (event: OcrPositionEvent) => void) => () => void;
      onStatePatch: (cb: (patch: RuntimeStatePatch) => void) => () => void;
    };
  }
}

export {};
