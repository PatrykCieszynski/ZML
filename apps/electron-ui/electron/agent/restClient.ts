import type { AgentHealthDto } from "@zml/shared";

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

  private async getJson(pathname: string): Promise<unknown> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);

    try {
      const response = await this.fetchImpl(new URL(pathname, this.baseUrl), {
        method: "GET",
        headers: { accept: "application/json" },
        signal: controller.signal,
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
