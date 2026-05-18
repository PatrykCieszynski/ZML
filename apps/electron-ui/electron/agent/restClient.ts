import {
  isRunWire,
  startRunRequestToWire,
  stopRunRequestToWire,
  wireToRunDto,
  type AgentHealthDto,
  type RunDto,
  type StartRunRequest,
  type StopRunRequest,
} from "@zml/shared";

type FetchLike = typeof fetch;

type AgentRestClientOptions = {
  baseUrl: string;
  timeoutMs?: number;
  fetchImpl?: FetchLike;
};

export class AgentRestClient {
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
    if (!isAgentHealthDto(data)) {
      throw new Error("Agent /health returned an invalid payload");
    }
    return data;
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

  private async getJson(pathname: string): Promise<unknown> {
    return this.requestJson("GET", pathname);
  }

  private async postJson(pathname: string, body: unknown): Promise<unknown> {
    return this.requestJson("POST", pathname, body);
  }

  private async requestJson(method: "GET" | "POST", pathname: string, body?: unknown): Promise<unknown> {
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

function isAgentHealthDto(value: unknown): value is AgentHealthDto {
  if (typeof value !== "object" || value === null) return false;
  const record = value as Record<string, unknown>;
  return typeof record.status === "string";
}
