import { safeStorage } from "electron";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";

export type StoredCloudCredential = {
  tokenId: string;
  token: string;
  label: string | null;
  createdAt: string;
};

type CredentialEnvelope = {
  version: 1;
  encrypted: string;
};

export interface CloudCredentialStoreLike {
  load(): Promise<StoredCloudCredential | null>;
  save(credential: StoredCloudCredential): Promise<void>;
  delete(): Promise<void>;
}

export class CloudCredentialStore implements CloudCredentialStoreLike {
  private readonly filePath: string;

  constructor(filePath: string) {
    this.filePath = filePath;
  }

  async load(): Promise<StoredCloudCredential | null> {
    let raw: string;
    try {
      raw = await readFile(this.filePath, "utf8");
    } catch (error) {
      if (isNodeError(error) && error.code === "ENOENT") return null;
      throw error;
    }

    if (!safeStorage.isEncryptionAvailable()) {
      throw new Error("Secure credential storage is unavailable on this system");
    }

    let envelope: CredentialEnvelope;
    try {
      const parsed = JSON.parse(raw) as unknown;
      if (!isRecord(parsed) || parsed.version !== 1 || typeof parsed.encrypted !== "string") {
        throw new Error("Invalid credential envelope");
      }
      envelope = { version: 1, encrypted: parsed.encrypted };
    } catch (error) {
      throw new Error("Stored ZML Cloud credential is invalid", { cause: error });
    }

    try {
      const plaintext = safeStorage.decryptString(Buffer.from(envelope.encrypted, "base64"));
      return parseCredential(JSON.parse(plaintext) as unknown);
    } catch (error) {
      throw new Error("Stored ZML Cloud credential could not be decrypted", { cause: error });
    }
  }

  async save(credential: StoredCloudCredential): Promise<void> {
    if (!safeStorage.isEncryptionAvailable()) {
      throw new Error("Secure credential storage is unavailable on this system");
    }

    const plaintext = JSON.stringify(credential);
    const encrypted = safeStorage.encryptString(plaintext).toString("base64");
    const envelope: CredentialEnvelope = { version: 1, encrypted };
    await mkdir(path.dirname(this.filePath), { recursive: true });
    await writeFile(this.filePath, `${JSON.stringify(envelope)}\n`, {
      encoding: "utf8",
      mode: 0o600,
    });
  }

  async delete(): Promise<void> {
    await rm(this.filePath, { force: true });
  }
}

function parseCredential(value: unknown): StoredCloudCredential {
  if (!isRecord(value)) throw new Error("Invalid credential payload");
  const tokenId = requiredString(value.tokenId, "token id");
  const token = requiredString(value.token, "sync token");
  const createdAt = requiredString(value.createdAt, "creation time");
  if (!token.startsWith("zml_")) throw new Error("Invalid sync token format");
  return {
    tokenId,
    token,
    label: typeof value.label === "string" ? value.label : null,
    createdAt,
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

function isNodeError(error: unknown): error is NodeJS.ErrnoException {
  return error instanceof Error && "code" in error;
}
