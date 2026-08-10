import { describe, expect, it, vi } from "vitest";

import { CloudConnectionService } from "./cloudConnectionService";
import type {
  CloudPairingClientLike,
  CloudPairingStatus,
  CreatedCloudPairing,
  ExchangedCloudCredential,
} from "./cloudPairingClient";
import type {
  CloudCredentialStoreLike,
  StoredCloudCredential,
} from "./cloudCredentialStore";

class FakePairingClient implements CloudPairingClientLike {
  readonly created: CreatedCloudPairing = {
    id: "pairing-id",
    deviceSecret: "device-secret",
    browserCode: "browser-code",
    label: "ZML Desktop",
    expiresAt: new Date(Date.now() + 60_000).toISOString(),
    pollAfterSeconds: 2,
  };
  readonly status: CloudPairingStatus = {
    id: this.created.id,
    label: this.created.label,
    status: "approved",
    expiresAt: this.created.expiresAt,
  };
  readonly issued: ExchangedCloudCredential = {
    id: "token-id",
    token: "zml_test_token",
    label: "ZML Desktop",
    createdAt: "2026-08-10T17:00:00.000Z",
  };

  createPairing = vi.fn(async () => this.created);
  pollPairing = vi.fn(async () => this.status);
  exchangePairing = vi.fn(async () => this.issued);
}

class FakeCredentialStore implements CloudCredentialStoreLike {
  credential: StoredCloudCredential | null = null;

  load = vi.fn(async () => this.credential);
  save = vi.fn(async (credential: StoredCloudCredential) => {
    this.credential = credential;
  });
  delete = vi.fn(async () => {
    this.credential = null;
  });
}

function createService({
  pairingClient = new FakePairingClient(),
  credentialStore = new FakeCredentialStore(),
}: {
  pairingClient?: FakePairingClient;
  credentialStore?: FakeCredentialStore;
} = {}) {
  let openedUrl: string | null = null;
  const openExternal = vi.fn(async (url: string) => {
    openedUrl = url;
  });
  const applyCredential = vi.fn(async (_token: string | null, _restartBackend: boolean) => undefined);
  const onState = vi.fn();
  const service = new CloudConnectionService({
    pairingClient,
    credentialStore,
    approvalBaseUrl: "https://zml-atlas.example",
    openExternal,
    applyCredential,
    canApplyCredential: () => true,
    onState,
  });
  return {
    service,
    pairingClient,
    credentialStore,
    openExternal,
    getOpenedUrl: () => openedUrl,
    applyCredential,
    onState,
  };
}

describe("CloudConnectionService", () => {
  it("restores a securely stored credential before backend startup", async () => {
    const credentialStore = new FakeCredentialStore();
    credentialStore.credential = {
      tokenId: "stored-id",
      token: "zml_stored_token",
      label: "ZML Desktop",
      createdAt: "2026-08-10T17:00:00.000Z",
    };
    const { service, applyCredential } = createService({ credentialStore });

    const state = await service.restore();

    expect(state.status).toBe("connected");
    expect(state.credentialSource).toBe("secure_store");
    expect(applyCredential).toHaveBeenCalledWith("zml_stored_token", false);
  });

  it("pairs through the browser and activates the issued credential", async () => {
    const {
      service,
      pairingClient,
      credentialStore,
      openExternal,
      getOpenedUrl,
      applyCredential,
    } = createService();

    const state = await service.connect();

    expect(state.status).toBe("connected");
    expect(state.credentialSource).toBe("secure_store");
    expect(pairingClient.createPairing).toHaveBeenCalledWith("ZML Desktop");
    expect(openExternal).toHaveBeenCalledTimes(1);
    const openedUrl = getOpenedUrl();
    expect(openedUrl).not.toBeNull();
    const approvalUrl = new URL(openedUrl ?? "https://invalid.example");
    expect(approvalUrl.origin).toBe("https://zml-atlas.example");
    expect(approvalUrl.pathname).toBe("/pair");
    expect(approvalUrl.searchParams.get("id")).toBe("pairing-id");
    expect(approvalUrl.searchParams.get("code")).toBe("browser-code");
    expect(pairingClient.pollPairing).toHaveBeenCalledWith("pairing-id", "device-secret");
    expect(pairingClient.exchangePairing).toHaveBeenCalledWith("pairing-id", "device-secret");
    expect(credentialStore.save).toHaveBeenCalledWith({
      tokenId: "token-id",
      token: "zml_test_token",
      label: "ZML Desktop",
      createdAt: "2026-08-10T17:00:00.000Z",
    });
    expect(applyCredential).toHaveBeenCalledWith("zml_test_token", true);
  });

  it("removes the local credential and restarts without cloud sync on disconnect", async () => {
    const credentialStore = new FakeCredentialStore();
    credentialStore.credential = {
      tokenId: "stored-id",
      token: "zml_stored_token",
      label: "ZML Desktop",
      createdAt: "2026-08-10T17:00:00.000Z",
    };
    const { service, applyCredential } = createService({ credentialStore });
    await service.restore();
    applyCredential.mockClear();

    const state = await service.disconnect();

    expect(state.status).toBe("disconnected");
    expect(credentialStore.delete).toHaveBeenCalledTimes(1);
    expect(applyCredential).toHaveBeenCalledWith(null, true);
  });
});
