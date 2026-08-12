import type {
  BackendHealthDto,
  ActiveMiningToolsDto,
  BootstrapState,
  CloudConnectionState,
  CreateMiningToolProfileRequest,
  MiningClaimDto,
  MiningToolProfileDto,
  MoveRunSegmentRequest,
  OcrCalibrationSnapshotDto,
  OcrPositionEvent,
  OcrRecalibrationResultDto,
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

declare global {
  interface Window {
    zml: {
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
      onPosition: (cb: (event: OcrPositionEvent) => void) => () => void;
      onStatePatch: (cb: (patch: RuntimeStatePatch) => void) => () => void;
    };
  }
}

export {};
