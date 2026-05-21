import type {
  AgentHealthDto,
  ActiveMiningToolsDto,
  BootstrapState,
  CreateMiningToolProfileRequest,
  MiningToolProfileDto,
  OcrPositionEvent,
  RuntimeStatePatch,
  RunDto,
  SetActiveMiningToolsRequest,
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
      listMiningTools: () => Promise<MiningToolProfileDto[]>;
      createMiningTool: (request: CreateMiningToolProfileRequest) => Promise<MiningToolProfileDto>;
      deleteMiningTool: (toolId: string) => Promise<void>;
      getActiveMiningTools: () => Promise<ActiveMiningToolsDto>;
      setActiveMiningTools: (request: SetActiveMiningToolsRequest) => Promise<ActiveMiningToolsDto>;
      onPosition: (cb: (event: OcrPositionEvent) => void) => () => void;
      onStatePatch: (cb: (patch: RuntimeStatePatch) => void) => () => void;
    };
  }
}

export {};
