import {
  isRunSegmentWire,
  isRunWireOrNull,
  isRunWire,
  createMiningToolProfileRequestToWire,
  isAgentHealthWire,
  isActiveMiningToolsWire,
  isMiningClaimWire,
  isMiningDropWire,
  isMiningLootItemWire,
  isMiningLootTotalWire,
  isMiningToolProfileWire,
  setActiveMiningToolsRequestToWire,
  startRunRequestToWire,
  stopRunRequestToWire,
  updateRunRequestToWire,
  wireToAgentHealthDto,
  wireToActiveMiningToolsDto,
  wireToMiningClaimDto,
  wireToMiningDropDto,
  wireToMiningLootItemDto,
  wireToMiningLootTotalDto,
  wireToMiningToolProfileDto,
  wireToRunSegmentDto,
  wireToRunDto,
  type ActiveMiningToolsDto,
  type AgentHealthDto,
  type CreateMiningToolProfileRequest,
  type MiningClaimDto,
  type MiningDropDto,
  type MiningLootItemDto,
  type MiningLootTotalDto,
  type MiningToolProfileDto,
  type RunDto,
  type RunSegmentDto,
  type SetActiveMiningToolsRequest,
  type StartRunRequest,
  type StopRunRequest,
  type UpdateRunRequest,
} from "@desktop/shared";

type FetchLike = typeof fetch;

type AgentRestClientOptions = {
  baseUrl: string;
  timeoutMs?: number;
  fetchImpl?: FetchLike;
};

export type AgentClient = {
  getHealth: () => Promise<AgentHealthDto>;
  getActiveRun: () => Promise<RunDto | null>;
  listRuns: () => Promise<RunDto[]>;
  resumeRun: (runId: number) => Promise<RunDto>;
  updateRun: (runId: number, request: UpdateRunRequest) => Promise<RunDto>;
  deleteRun: (runId: number) => Promise<RunDto>;
  listActiveRunSegments: () => Promise<RunSegmentDto[]>;
  listRunSegments: (runId: number) => Promise<RunSegmentDto[]>;
  startRun: (request: StartRunRequest) => Promise<RunDto>;
  stopRun: (request: StopRunRequest) => Promise<RunDto>;
  listMiningClaims: (request?: ListMiningClaimsRequest) => Promise<MiningClaimDto[]>;
  markMiningClaimDepleted: (
    claimId: string,
    request?: MarkMiningClaimDepletedRequest,
  ) => Promise<MiningClaimDto>;
  ignoreMiningClaim: (claimId: string, request?: IgnoreMiningClaimRequest) => Promise<MiningClaimDto>;
  listMiningDrops: (request?: ListMiningDropsRequest) => Promise<MiningDropDto[]>;
  listMiningLoot: (request?: ListMiningLootRequest) => Promise<MiningLootItemDto[]>;
  listMiningLootTotals: (request?: ListMiningLootTotalsRequest) => Promise<MiningLootTotalDto[]>;
  listMiningTools: () => Promise<MiningToolProfileDto[]>;
  createMiningTool: (request: CreateMiningToolProfileRequest) => Promise<MiningToolProfileDto>;
  deleteMiningTool: (toolId: string) => Promise<void>;
  getActiveMiningTools: () => Promise<ActiveMiningToolsDto>;
  setActiveMiningTools: (request: SetActiveMiningToolsRequest) => Promise<ActiveMiningToolsDto>;
};

export type ListMiningClaimsRequest = {
  active?: boolean;
  runId?: number;
  activeRun?: boolean;
};

export type IgnoreMiningClaimRequest = {
  reason?: string | null;
};

export type MarkMiningClaimDepletedRequest = {
  reason?: string | null;
};

export type ListMiningDropsRequest = {
  windowMinutes?: number;
  runId?: number;
  activeRun?: boolean;
};

export type ListMiningLootRequest = {
  runId?: number;
  activeRun?: boolean;
};

export type ListMiningLootTotalsRequest = {
  runId?: number;
  segmentId?: string;
  activeRun?: boolean;
};

export class AgentRestClient implements AgentClient {
  private readonly baseUrl: URL;
  private readonly timeoutMs: number;
  private readonly fetchImpl: FetchLike;

  constructor({ baseUrl, timeoutMs = 3_000, fetchImpl = fetch }: AgentRestClientOptions) {
    this.baseUrl = new URL(normalizeBaseUrl(baseUrl));
    this.timeoutMs = timeoutMs;
    this.fetchImpl = fetchImpl;
  }

  async getHealth(): Promise<AgentHealthDto> {
    const data = await this.getJson("/health");
    if (!isAgentHealthWire(data)) {
      throw new Error("Agent /health returned an invalid payload");
    }
    return wireToAgentHealthDto(data);
  }

  async getActiveRun(): Promise<RunDto | null> {
    const data = await this.getJson("/api/v1/runs/active");
    if (!isRunWireOrNull(data)) {
      throw new Error("Agent active run returned an invalid payload");
    }
    return data === null ? null : wireToRunDto(data);
  }

  async listRuns(): Promise<RunDto[]> {
    const data = await this.getJson("/api/v1/runs");
    if (!Array.isArray(data) || !data.every(isRunWire)) {
      throw new Error("Agent runs returned an invalid payload");
    }
    return data.map(wireToRunDto);
  }

  async resumeRun(runId: number): Promise<RunDto> {
    const data = await this.postJson(`/api/v1/runs/${encodeURIComponent(String(runId))}/resume`, {});
    if (!isRunWire(data)) {
      throw new Error("Agent resume run returned an invalid payload");
    }
    return wireToRunDto(data);
  }

  async updateRun(runId: number, request: UpdateRunRequest): Promise<RunDto> {
    const data = await this.patchJson(
      `/api/v1/runs/${encodeURIComponent(String(runId))}`,
      updateRunRequestToWire(request),
    );
    if (!isRunWire(data)) {
      throw new Error("Agent update run returned an invalid payload");
    }
    return wireToRunDto(data);
  }

  async deleteRun(runId: number): Promise<RunDto> {
    const data = await this.requestJson("DELETE", `/api/v1/runs/${encodeURIComponent(String(runId))}`);
    if (!isRunWire(data)) {
      throw new Error("Agent delete run returned an invalid payload");
    }
    return wireToRunDto(data);
  }

  async listActiveRunSegments(): Promise<RunSegmentDto[]> {
    const data = await this.getJson("/api/v1/runs/active/segments");
    if (!Array.isArray(data) || !data.every(isRunSegmentWire)) {
      throw new Error("Agent active run segments returned an invalid payload");
    }
    return data.map(wireToRunSegmentDto);
  }

  async listRunSegments(runId: number): Promise<RunSegmentDto[]> {
    const data = await this.getJson(`/api/v1/runs/${encodeURIComponent(String(runId))}/segments`);
    if (!Array.isArray(data) || !data.every(isRunSegmentWire)) {
      throw new Error("Agent run segments returned an invalid payload");
    }
    return data.map(wireToRunSegmentDto);
  }

  async startRun(request: StartRunRequest): Promise<RunDto> {
    const data = await this.postJson("/api/v1/runs/start", startRunRequestToWire(request));
    if (!isRunWire(data)) {
      throw new Error("Agent start run returned an invalid payload");
    }
    return wireToRunDto(data);
  }

  async stopRun(request: StopRunRequest): Promise<RunDto> {
    const data = await this.postJson("/api/v1/runs/stop", stopRunRequestToWire(request));
    if (!isRunWire(data)) {
      throw new Error("Agent stop run returned an invalid payload");
    }
    return wireToRunDto(data);
  }

  async listMiningClaims(request: ListMiningClaimsRequest = {}): Promise<MiningClaimDto[]> {
    const params = new URLSearchParams();
    if (request.active !== undefined) {
      params.set("active", request.active ? "yes" : "no");
    }
    if (request.runId !== undefined) {
      params.set("run_id", String(request.runId));
    }
    if (request.activeRun !== undefined) {
      params.set("active_run", request.activeRun ? "yes" : "no");
    }

    const serializedParams = params.toString();
    const query = serializedParams ? `?${serializedParams}` : "";
    const data = await this.getJson(`/api/v1/mining/claims${query}`);
    if (!Array.isArray(data) || !data.every(isMiningClaimWire)) {
      throw new Error("Agent mining claims returned an invalid payload");
    }
    return data.map(wireToMiningClaimDto);
  }

  async ignoreMiningClaim(
    claimId: string,
    request: IgnoreMiningClaimRequest = {},
  ): Promise<MiningClaimDto> {
    const data = await this.postJson(
      `/api/v1/mining/claims/${encodeURIComponent(claimId)}/ignore`,
      { reason: request.reason ?? null },
    );
    if (!isMiningClaimWire(data)) {
      throw new Error("Agent ignore mining claim returned an invalid payload");
    }
    return wireToMiningClaimDto(data);
  }

  async markMiningClaimDepleted(
    claimId: string,
    request: MarkMiningClaimDepletedRequest = {},
  ): Promise<MiningClaimDto> {
    const data = await this.postJson(
      `/api/v1/mining/claims/${encodeURIComponent(claimId)}/deplete`,
      { reason: request.reason ?? null },
    );
    if (!isMiningClaimWire(data)) {
      throw new Error("Agent mark mining claim depleted returned an invalid payload");
    }
    return wireToMiningClaimDto(data);
  }

  async listMiningDrops(request: ListMiningDropsRequest = {}): Promise<MiningDropDto[]> {
    const params = new URLSearchParams();
    if (request.windowMinutes !== undefined) {
      params.set("window_minutes", String(request.windowMinutes));
    }
    if (request.runId !== undefined) {
      params.set("run_id", String(request.runId));
    }
    if (request.activeRun !== undefined) {
      params.set("active_run", request.activeRun ? "yes" : "no");
    }

    const serializedParams = params.toString();
    const query = serializedParams ? `?${serializedParams}` : "";
    const data = await this.getJson(`/api/v1/mining/drops${query}`);
    if (!Array.isArray(data) || !data.every(isMiningDropWire)) {
      throw new Error("Agent mining drops returned an invalid payload");
    }
    return data.map(wireToMiningDropDto);
  }

  async listMiningLoot(request: ListMiningLootRequest = {}): Promise<MiningLootItemDto[]> {
    const params = new URLSearchParams();
    if (request.runId !== undefined) {
      params.set("run_id", String(request.runId));
    }
    if (request.activeRun !== undefined) {
      params.set("active_run", request.activeRun ? "yes" : "no");
    }

    const serializedParams = params.toString();
    const query = serializedParams ? `?${serializedParams}` : "";
    const data = await this.getJson(`/api/v1/mining/loot${query}`);
    if (!Array.isArray(data) || !data.every(isMiningLootItemWire)) {
      throw new Error("Agent mining loot returned an invalid payload");
    }
    return data.map(wireToMiningLootItemDto);
  }

  async listMiningLootTotals(
    request: ListMiningLootTotalsRequest = {},
  ): Promise<MiningLootTotalDto[]> {
    const params = new URLSearchParams();
    if (request.runId !== undefined) {
      params.set("run_id", String(request.runId));
    }
    if (request.segmentId !== undefined) {
      params.set("segment_id", request.segmentId);
    }
    if (request.activeRun !== undefined) {
      params.set("active_run", request.activeRun ? "yes" : "no");
    }

    const serializedParams = params.toString();
    const query = serializedParams ? `?${serializedParams}` : "";
    const data = await this.getJson(`/api/v1/mining/loot/totals${query}`);
    if (!Array.isArray(data) || !data.every(isMiningLootTotalWire)) {
      throw new Error("Agent mining loot totals returned an invalid payload");
    }
    return data.map(wireToMiningLootTotalDto);
  }

  async listMiningTools(): Promise<MiningToolProfileDto[]> {
    const data = await this.getJson("/api/v1/mining/tools");
    if (!Array.isArray(data) || !data.every(isMiningToolProfileWire)) {
      throw new Error("Agent mining tools returned an invalid payload");
    }
    return data.map(wireToMiningToolProfileDto);
  }

  async createMiningTool(request: CreateMiningToolProfileRequest): Promise<MiningToolProfileDto> {
    const data = await this.postJson(
      "/api/v1/mining/tools",
      createMiningToolProfileRequestToWire(request),
    );
    if (!isMiningToolProfileWire(data)) {
      throw new Error("Agent create mining tool returned an invalid payload");
    }
    return wireToMiningToolProfileDto(data);
  }

  async deleteMiningTool(toolId: string): Promise<void> {
    await this.deleteJson(`/api/v1/mining/tools/${encodeURIComponent(toolId)}`);
  }

  async getActiveMiningTools(): Promise<ActiveMiningToolsDto> {
    const data = await this.getJson("/api/v1/mining/tools/active");
    if (!isActiveMiningToolsWire(data)) {
      throw new Error("Agent active mining tools returned an invalid payload");
    }
    return wireToActiveMiningToolsDto(data);
  }

  async setActiveMiningTools(request: SetActiveMiningToolsRequest): Promise<ActiveMiningToolsDto> {
    const data = await this.putJson(
      "/api/v1/mining/tools/active",
      setActiveMiningToolsRequestToWire(request),
    );
    if (!isActiveMiningToolsWire(data)) {
      throw new Error("Agent set active mining tools returned an invalid payload");
    }
    return wireToActiveMiningToolsDto(data);
  }

  private async getJson(pathname: string): Promise<unknown> {
    return this.requestJson("GET", pathname);
  }

  private async postJson(pathname: string, body: unknown): Promise<unknown> {
    return this.requestJson("POST", pathname, body);
  }

  private async putJson(pathname: string, body: unknown): Promise<unknown> {
    return this.requestJson("PUT", pathname, body);
  }

  private async patchJson(pathname: string, body: unknown): Promise<unknown> {
    return this.requestJson("PATCH", pathname, body);
  }

  private async deleteJson(pathname: string): Promise<void> {
    await this.requestJson("DELETE", pathname);
  }

  private async requestJson(method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE", pathname: string, body?: unknown): Promise<unknown> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);

    try {
      const response = await this.fetchImpl(new URL(pathname, this.baseUrl), {
        method,
        headers: {
          accept: "application/json",
          ...(body === undefined ? {} : { "content-type": "application/json" }),
        },
        signal: controller.signal,
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      });

      if (!response.ok) {
        throw new Error(`Agent request failed: ${response.status} ${response.statusText}`);
      }

      if (response.status === 204) {
        return undefined;
      }

      return response.json() as Promise<unknown>;
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") {
        throw new Error(`Agent request timed out after ${this.timeoutMs}ms`);
      }
      throw error;
    } finally {
      clearTimeout(timeout);
    }
  }
}

function normalizeBaseUrl(baseUrl: string): string {
  if (/^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//.test(baseUrl)) return baseUrl;
  return `http://${baseUrl}`;
}

