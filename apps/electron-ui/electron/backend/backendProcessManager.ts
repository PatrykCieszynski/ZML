import path from "node:path";
import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";

const HEALTH_POLL_INTERVAL_MS = 250;
const HEALTH_REQUEST_TIMEOUT_MS = 1_500;
const BACKEND_START_TIMEOUT_MS = 15_000;
const BACKEND_STOP_TIMEOUT_MS = 5_000;
const BACKEND_RESTART_DELAYS_MS = [500, 1_000, 2_000, 4_000];

export type BackendLaunchSpec = {
  command: string;
  args: string[];
  cwd: string;
  environment?: Record<string, string>;
};

export class BackendProcessManager {
  private child: ChildProcessWithoutNullStreams | null = null;
  private restartTimer: NodeJS.Timeout | null = null;
  private stopping = false;
  private restartIndex = 0;

  constructor(
    private readonly launchSpec: BackendLaunchSpec,
    private readonly baseUrl: string,
  ) {}

  async start(): Promise<void> {
    if (this.child || this.stopping) return;
    this.spawnBackend();
    const healthy = await this.waitForHealth(BACKEND_START_TIMEOUT_MS);
    if (!healthy) {
      await this.stop();
      throw new Error("Managed backend did not become healthy in time");
    }
  }

  async stop(): Promise<void> {
    this.stopping = true;
    this.clearRestartTimer();
    const child = this.child;
    this.child = null;
    if (!child || child.exitCode !== null) return;

    try {
      child.stdin.end();
    } catch {
      // The process may already be exiting.
    }

    const exited = await waitForExit(child, BACKEND_STOP_TIMEOUT_MS);
    if (!exited && child.exitCode === null) child.kill();
  }

  private spawnBackend(): void {
    const child = spawn(this.launchSpec.command, this.launchSpec.args, {
      cwd: this.launchSpec.cwd,
      env: {
        ...process.env,
        ...this.launchSpec.environment,
      },
      stdio: ["pipe", "pipe", "pipe"],
      windowsHide: true,
    });
    this.child = child;

    child.stdout.on("data", (chunk) => {
      process.stdout.write(`[backend] ${chunk}`);
    });
    child.stderr.on("data", (chunk) => {
      process.stderr.write(`[backend] ${chunk}`);
    });
    child.on("error", (error) => {
      console.error("[backend] process error", error);
    });
    child.on("exit", (code, signal) => {
      if (this.child === child) this.child = null;
      console.info(`[backend] exited code=${code} signal=${signal}`);
      if (!this.stopping) this.scheduleRestart();
    });
  }

  private scheduleRestart(): void {
    if (this.restartTimer) return;
    const delay =
      BACKEND_RESTART_DELAYS_MS[
        Math.min(this.restartIndex, BACKEND_RESTART_DELAYS_MS.length - 1)
      ];
    this.restartIndex += 1;
    this.restartTimer = setTimeout(async () => {
      this.restartTimer = null;
      if (this.stopping || this.child) return;
      this.spawnBackend();
      if (await this.waitForHealth(BACKEND_START_TIMEOUT_MS)) {
        this.restartIndex = 0;
      }
    }, delay);
  }

  private async waitForHealth(timeoutMs: number): Promise<boolean> {
    const deadline = Date.now() + timeoutMs;
    while (!this.stopping && Date.now() < deadline) {
      if (await checkBackendHealth(this.baseUrl)) {
        console.info("[backend] health check passed");
        return true;
      }
      await delay(HEALTH_POLL_INTERVAL_MS);
    }
    return false;
  }

  private clearRestartTimer(): void {
    if (this.restartTimer !== null) clearTimeout(this.restartTimer);
    this.restartTimer = null;
  }
}

export function createBackendLaunchSpec({
  isPackaged,
  resourcesPath,
  appRoot,
}: {
  isPackaged: boolean;
  resourcesPath: string;
  appRoot: string;
}): BackendLaunchSpec {
  if (isPackaged) {
    const backendDir = path.join(resourcesPath, "backend");
    const ocrAgentExecutable = path.join(
      resourcesPath,
      "ocr-agent",
      "zml-ocr-agent.exe",
    );
    return {
      command: path.join(backendDir, "zml-game-bridge.exe"),
      args: ["serve", "--mode", "live"],
      cwd: backendDir,
      environment: {
        ZML_OCR_AGENT_PATH: ocrAgentExecutable,
      },
    };
  }

  const repoRoot = path.resolve(appRoot, "..", "..");
  const backendDir = path.resolve(appRoot, "..", "game-bridge");
  const workspaceVenv = path.join(repoRoot, ".venv");
  const pythonExecutable =
    process.platform === "win32"
      ? path.join(workspaceVenv, "Scripts", "python.exe")
      : path.join(workspaceVenv, "bin", "python");
  const ocrAgentExecutable =
    process.platform === "win32"
      ? path.join(workspaceVenv, "Scripts", "zml-ocr-agent.exe")
      : path.join(workspaceVenv, "bin", "zml-ocr-agent");
  return {
    command: pythonExecutable,
    args: ["-m", "zml_game_bridge.dev_cli", "serve", "--mode", "live"],
    cwd: backendDir,
    environment: {
      ZML_OCR_AGENT_PATH: ocrAgentExecutable,
    },
  };
}

export function shouldManageBackend({
  mocksEnabled,
  backendUrlOverridden,
  explicitValue,
}: {
  mocksEnabled: boolean;
  backendUrlOverridden: boolean;
  explicitValue: string | undefined;
}): boolean {
  if (mocksEnabled) return false;
  if (explicitValue !== undefined) {
    return ["1", "true", "yes", "on"].includes(
      explicitValue.trim().toLowerCase(),
    );
  }
  return !backendUrlOverridden;
}

async function checkBackendHealth(baseUrl: string): Promise<boolean> {
  const controller = new AbortController();
  const timeout = setTimeout(
    () => controller.abort(),
    HEALTH_REQUEST_TIMEOUT_MS,
  );
  try {
    const url = new URL("/health", normalizeBaseUrl(baseUrl));
    const response = await fetch(url, { signal: controller.signal });
    return response.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timeout);
  }
}

function normalizeBaseUrl(baseUrl: string): string {
  return baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function waitForExit(
  child: ChildProcessWithoutNullStreams,
  timeoutMs: number,
): Promise<boolean> {
  if (child.exitCode !== null) return Promise.resolve(true);
  return new Promise((resolve) => {
    const timeout = setTimeout(() => {
      child.off("exit", onExit);
      resolve(false);
    }, timeoutMs);
    const onExit = () => {
      clearTimeout(timeout);
      resolve(true);
    };
    child.once("exit", onExit);
  });
}
