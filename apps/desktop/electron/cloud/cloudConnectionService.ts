import type { CloudConnectionState } from "@desktop/shared";
import type {
  CloudPairingClientLike,
  ExchangedCloudCredential,
} from "./cloudPairingClient.ts";
import type {
  CloudCredentialStoreLike,
  StoredCloudCredential,
} from "./cloudCredentialStore.ts";

export type ApplyCloudCredential = (
  token: string | null,
  restartBackend: boolean,
) => Promise<void>;

type CloudConnectionServiceOptions = {
  pairingClient: CloudPairingClientLike;
  credentialStore: CloudCredentialStoreLike;
  approvalBaseUrl: string;
  openExternal: (url: string) => Promise<void>;
  applyCredential: ApplyCloudCredential;
  canApplyCredential: () => boolean;
  onState: (state: CloudConnectionState) => void;
  environmentToken?: string;
};

export class CloudConnectionService {
  private readonly pairingClient: CloudPairingClientLike;
  private readonly credentialStore: CloudCredentialStoreLike;
  private readonly approvalBaseUrl: string;
  private readonly openExternal: (url: string) => Promise<void>;
  private readonly applyCredential: ApplyCloudCredential;
  private readonly canApplyCredential: () => boolean;
  private readonly onState: (state: CloudConnectionState) => void;
  private readonly environmentToken?: string;

  private state: CloudConnectionState = { status: "disconnected" };
  private attempt = 0;

  constructor(options: CloudConnectionServiceOptions) {
    this.pairingClient = options.pairingClient;
    this.credentialStore = options.credentialStore;
    this.approvalBaseUrl = options.approvalBaseUrl.replace(/\/+$/, "");
    this.openExternal = options.openExternal;
    this.applyCredential = options.applyCredential;
    this.canApplyCredential = options.canApplyCredential;
    this.onState = options.onState;
    this.environmentToken = normalizeToken(options.environmentToken);
  }

  getState(): CloudConnectionState {
    return { ...this.state };
  }

  async restore(): Promise<CloudConnectionState> {
    try {
      if (this.environmentToken !== undefined) {
        await this.applyCredential(this.environmentToken, false);
        return this.setState({
          status: "connected",
          credentialSource: "environment",
          connectedAtTsMs: Date.now(),
        });
      }

      const credential = await this.credentialStore.load();
      if (credential === null) {
        return this.setState({ status: "disconnected" });
      }

      await this.applyCredential(credential.token, false);
      return this.setState({
        status: "connected",
        credentialSource: "secure_store",
        connectedAtTsMs: parseTimestamp(credential.createdAt),
      });
    } catch (error) {
      return this.setState({
        status: "error",
        lastError: errorToMessage(error),
      });
    }
  }

  async connect(): Promise<CloudConnectionState> {
    if (this.environmentToken !== undefined) return this.getState();
    if (this.state.status === "connected") return this.getState();
    if (!this.canApplyCredential()) {
      return this.setState({
        status: "error",
        lastError: "ZML Cloud connection requires the Desktop-managed local Backend",
      });
    }

    const attempt = ++this.attempt;
    this.setState({ status: "connecting" });

    try {
      const pairing = await this.pairingClient.createPairing("ZML Desktop");
      if (!this.isCurrentAttempt(attempt)) return this.getState();

      const expiresAtTsMs = parseTimestamp(pairing.expiresAt);
      this.setState({
        status: "waiting_for_approval",
        pairingExpiresAtTsMs: expiresAtTsMs,
      });

      const approvalUrl = new URL("/pair", `${this.approvalBaseUrl}/`);
      approvalUrl.searchParams.set("id", pairing.id);
      approvalUrl.searchParams.set("code", pairing.browserCode);
      await this.openExternal(approvalUrl.toString());

      while (this.isCurrentAttempt(attempt) && Date.now() < expiresAtTsMs) {
        const status = await this.pairingClient.pollPairing(pairing.id, pairing.deviceSecret);
        if (!this.isCurrentAttempt(attempt)) return this.getState();

        if (status.status === "approved") {
          const issued = await this.pairingClient.exchangePairing(pairing.id, pairing.deviceSecret);
          if (!this.isCurrentAttempt(attempt)) return this.getState();
          await this.finishConnection(issued);
          return this.getState();
        }
        if (status.status === "expired") {
          throw new Error("ZML Cloud connection request expired");
        }
        if (status.status === "consumed") {
          throw new Error("ZML Cloud connection request was already used");
        }

        await delay(pairing.pollAfterSeconds * 1_000);
      }

      if (this.isCurrentAttempt(attempt)) {
        throw new Error("ZML Cloud connection request expired");
      }
      return this.getState();
    } catch (error) {
      if (!this.isCurrentAttempt(attempt)) return this.getState();
      return this.setState({
        status: "error",
        lastError: errorToMessage(error),
      });
    }
  }

  async disconnect(): Promise<CloudConnectionState> {
    ++this.attempt;

    if (this.environmentToken !== undefined) {
      return this.setState({
        status: "error",
        credentialSource: "environment",
        connectedAtTsMs: this.state.connectedAtTsMs,
        lastError: "ZML Cloud is configured by environment variables and cannot be disconnected here",
      });
    }

    if (this.state.status === "connecting" || this.state.status === "waiting_for_approval") {
      return this.setState({ status: "disconnected" });
    }

    try {
      await this.credentialStore.delete();
      if (this.canApplyCredential()) {
        await this.applyCredential(null, true);
      }
      return this.setState({ status: "disconnected" });
    } catch (error) {
      return this.setState({
        status: "error",
        lastError: errorToMessage(error),
      });
    }
  }

  private async finishConnection(issued: ExchangedCloudCredential): Promise<void> {
    const credential: StoredCloudCredential = {
      tokenId: issued.id,
      token: issued.token,
      label: issued.label,
      createdAt: issued.createdAt,
    };
    await this.credentialStore.save(credential);
    await this.applyCredential(credential.token, true);
    this.setState({
      status: "connected",
      credentialSource: "secure_store",
      connectedAtTsMs: parseTimestamp(credential.createdAt),
    });
  }

  private isCurrentAttempt(attempt: number): boolean {
    return this.attempt === attempt;
  }

  private setState(next: CloudConnectionState): CloudConnectionState {
    this.state = {
      ...next,
      lastError: next.lastError ?? null,
    };
    const snapshot = this.getState();
    this.onState(snapshot);
    return snapshot;
  }
}

function normalizeToken(value: string | undefined): string | undefined {
  const normalized = value?.trim();
  return normalized ? normalized : undefined;
}

function parseTimestamp(value: string): number {
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) throw new Error("ZML Cloud returned an invalid timestamp");
  return timestamp;
}

function errorToMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
