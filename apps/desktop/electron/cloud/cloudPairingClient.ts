export type CreatedCloudPairing = {
  id: string;
  deviceSecret: string;
  browserCode: string;
  label: string | null;
  expiresAt: string;
  pollAfterSeconds: number;
};

export type CloudPairingStatus = {
  id: string;
  label: string | null;
  status: "pending" | "approved" | "expired" | "consumed";
  expiresAt: string;
};

export type ExchangedCloudCredential = {
  id: string;
  token: string;
  label: string | null;
  createdAt: string;
};

export interface CloudPairingClientLike {
  createPairing(label?: string): Promise<CreatedCloudPairing>;
  pollPairing(pairingId: string, deviceSecret: string): Promise<CloudPairingStatus>;
  exchangePairing(pairingId: string, deviceSecret: string): Promise<ExchangedCloudCredential>;
}

export class CloudPairingClient implements CloudPairingClientLike {
  private readonly baseUrl: string;
  private readonly timeoutMs: number;

  constructor({ baseUrl, timeoutMs = 10_000 }: { baseUrl: string; timeoutMs?: number }) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.timeoutMs = timeoutMs;
  }

  async createPairing(label?: string): Promise<CreatedCloudPairing> {
    const payload = await this.requestJson("/api/v1/pairing", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(label ? { label } : {}),
    });
    return parseCreatedPairing(payload);
  }

  async pollPairing(pairingId: string, deviceSecret: string): Promise<CloudPairingStatus> {
    const payload = await this.requestJson(`/api/v1/pairing/${encodeURIComponent(pairingId)}`, {
      headers: { "X-ZML-Pairing-Secret": deviceSecret },
    });
    return parsePairingStatus(payload);
  }

  async exchangePairing(pairingId: string, deviceSecret: string): Promise<ExchangedCloudCredential> {
    const payload = await this.requestJson(
      `/api/v1/pairing/${encodeURIComponent(pairingId)}/exchange`,
      {
        method: "POST",
        headers: { "X-ZML-Pairing-Secret": deviceSecret },
      },
    );
    return parseExchangedCredential(payload);
  }

  private async requestJson(pathname: string, init: RequestInit): Promise<unknown> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const response = await fetch(new URL(pathname, `${this.baseUrl}/`), {
        ...init,
        headers: {
          Accept: "application/json",
          "User-Agent": "ZML-Desktop/1.2",
          ...init.headers,
        },
        signal: controller.signal,
      });
      if (!response.ok) {
        throw new Error(`ZML Cloud request failed (${response.status})`);
      }
      return await response.json();
    } catch (error) {
      if (controller.signal.aborted) {
        throw new Error("ZML Cloud request timed out", { cause: error });
      }
      throw error;
    } finally {
      clearTimeout(timeout);
    }
  }
}

function parseCreatedPairing(value: unknown): CreatedCloudPairing {
  if (!isRecord(value)) throw new Error("Invalid pairing response");
  const id = requiredString(value.id, "pairing id");
  const deviceSecret = requiredString(value.deviceSecret, "device secret");
  const browserCode = requiredString(value.browserCode, "browser code");
  const expiresAt = requiredString(value.expiresAt, "expiry");
  const pollAfterSeconds = value.pollAfterSeconds;
  if (typeof pollAfterSeconds !== "number" || !Number.isFinite(pollAfterSeconds)) {
    throw new Error("Invalid pairing poll interval");
  }
  return {
    id,
    deviceSecret,
    browserCode,
    label: nullableString(value.label),
    expiresAt,
    pollAfterSeconds: Math.min(10, Math.max(1, pollAfterSeconds)),
  };
}

function parsePairingStatus(value: unknown): CloudPairingStatus {
  if (!isRecord(value)) throw new Error("Invalid pairing status response");
  const rawStatus = requiredString(value.status, "pairing status");
  if (!["pending", "approved", "expired", "consumed"].includes(rawStatus)) {
    throw new Error("Invalid pairing status");
  }
  return {
    id: requiredString(value.id, "pairing id"),
    label: nullableString(value.label),
    status: rawStatus as CloudPairingStatus["status"],
    expiresAt: requiredString(value.expiresAt, "expiry"),
  };
}

function parseExchangedCredential(value: unknown): ExchangedCloudCredential {
  if (!isRecord(value)) throw new Error("Invalid pairing exchange response");
  const token = requiredString(value.token, "sync token");
  if (!token.startsWith("zml_")) throw new Error("Invalid sync token format");
  return {
    id: requiredString(value.id, "token id"),
    token,
    label: nullableString(value.label),
    createdAt: requiredString(value.createdAt, "creation time"),
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requiredString(value: unknown, field: string): string {
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`Invalid ${field}`);
  }
  return value;
}

function nullableString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}
