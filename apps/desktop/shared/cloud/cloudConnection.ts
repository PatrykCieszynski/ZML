export type CloudConnectionStatus =
  | "disconnected"
  | "connecting"
  | "waiting_for_approval"
  | "connected"
  | "error";

export type CloudCredentialSource = "environment" | "secure_store";

export type CloudConnectionState = {
  status: CloudConnectionStatus;
  credentialSource?: CloudCredentialSource;
  connectedAtTsMs?: number;
  pairingExpiresAtTsMs?: number;
  lastError?: string | null;
};
