import type {
  AgentHealthDto,
  ActiveMiningToolsDto,
  BootstrapState,
  CreateMiningToolProfileRequest,
  MiningToolProfileDto,
  OcrPositionEvent,
  RuntimeStatePatch,
  RunDto,
  RunSegmentDto,
  SetActiveMiningToolsRequest,
  StartRunRequest,
  StopRunRequest,
  UpdateRunRequest,
  WindowType,
} from "@zml/shared";

declare global {
  interface Window {
    zml: {
      getBootstrapState: (windowType: WindowType) => Promise<BootstrapState>;
      getAgentHealth: () => Promise<AgentHealthDto>;
      getActiveRun: () => Promise<RunDto | null>;
      listRuns: () => Promise<RunDto[]>;
      resumeRun: (runId: number) => Promise<RunDto>;
      updateRun: (runId: number, request: UpdateRunRequest) => Promise<RunDto>;
      deleteRun: (runId: number) => Promise<RunDto>;
      listActiveRunSegments: () => Promise<RunSegmentDto[]>;
      listRunSegments: (runId: number) => Promise<RunSegmentDto[]>;
      toggleMapWindow: () => Promise<boolean>;
      toggleOverlayWindow: () => Promise<boolean>;
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
