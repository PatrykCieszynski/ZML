import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";

export type BackendLaunchSpec = {
  command: string;
  args: string[];
  cwd: string;
};

type BackendProcessManagerOptions = {
  baseUrl: string;
  launch: BackendLaunchSpec;
  startupTimeoutMs?: number;
  shutdownTimeoutMs?: number;
  maxRestartsPerMinute?: number;
};

const HEALTH_POLL_INTERVAL_MS = 250;
const HEALTH_REQUEST_TIMEOUT_MS = 750;
const RESTART_WINDOW_MS = 60_000;

export class BackendProcessManager {
  private readonly baseUrl: string;
  private readonly launch: BackendLaunchSpec;
  private readonly startupTimeoutMs: number;
  private readonly shutdownTimeoutMs: number;
  private readonly maxRestartsPerMinute: number;

  private child: ChildProcessWithoutNullStreams | null = null;
  private restartTimer: NodeJS.Timeout | null = null;
  private restartTimestamps: number[] = [];
  private stopping = false;
  private usingExternalBackend = false;

  constructor({
    baseUrl,
    launch,
    startupTimeoutMs = 60_000,
    shutdownTimeoutMs = 30_000,
    maxRestartsPerMinute = 3,
  }: BackendProcessManagerOptions) {
    this.baseUrl = baseUrl;
    this.launch = launch;
    this.startupTimeoutMs = startupTimeoutMs;
    this.shutdownTimeoutMs = shutdownTimeoutMs;
    this.maxRestartsPerMinute = maxRestartsPerMinute;
  }

  async start(): Promise<boolean> {
    if (this.child !== null) return this.waitUntilReady(this.startupTimeoutMs);

    this.stopping = false;
    this.usingExternalBackend = false;
    if (await checkBackendHealth(this.baseUrl)) {
      this.usingExternalBackend = true;
      console.info("[backend] using already running backend");
      return true;
    }
    if (this.stopping) return false;

    this.spawnBackend();
    const ready = await this.waitUntilReady(this.startupTimeoutMs);
    if (!ready) {
      console.error(`[backend] health check timed out after ${this.startupTimeoutMs}ms`);
    }
    return ready;
  }

  async stop(): Promise<void> {
    this.stopping = true;
    this.clearRestartTimer();

    if (this.usingExternalBackend) {
      this.usingExternalBackend = false;
      return;
    }

    const child = this.child;
    if (child === null) return;

    if (child.stdin.writable) {
      try {
        child.stdin.write("shutdown\n");
      } catch (error) {
        console.warn("[backend] failed to send graceful shutdown command", error);
      }
    }
    const stoppedGracefully = await waitForChildClose(child, this.shutdownTimeoutMs);
    if (!stoppedGracefully && this.child === child) {
      console.warn("[backend] graceful shutdown timed out; terminating process");
      child.kill();
      await waitForChildClose(child, 1_000);
    }
    if (this.child === child) this.child = null;
  }

  private spawnBackend(): void {
    if (!existsSync(this.launch.command)) {
      throw new Error(`Backend executable not found: ${this.launch.command}`);
    }

    console.info(
      `[backend] starting ${this.launch.command} ${this.launch.args.join(" ")}`,
    );
    const child = spawn(this.launch.command, this.launch.args, {
      cwd: this.launch.cwd,
      env: {
        ...process.env,
        PYTHONUNBUFFERED: "1",
        ZML_PARENT_MANAGED: "1",
      },
      shell: false,
      stdio: ["pipe", "pipe", "pipe"],
      windowsHide: true,
    });
    this.child = child;

    forwardBackendOutput(child);
    child.once("error", (error) => {
      console.error("[backend] process error", error);
    });
    child.stdin.on("error", (error) => {
      if (!this.stopping) console.error("[backend] stdin error", error);
    });
    child.once("close", (code, signal) => {
      if (this.child !== child) return;
      this.child = null;
      if (this.stopping) return;

      console.error(
        `[backend] exited unexpectedly code=${String(code)} signal=${String(signal)}`,
      );
      this.scheduleRestart();
    });
  }

  private scheduleRestart(): void {
    if (this.stopping || this.restartTimer !== null) return;

    const now = Date.now();
    this.restartTimestamps = this.restartTimestamps.filter(
      (timestamp) => now - timestamp < RESTART_WINDOW_MS,
    );
    if (this.restartTimestamps.length >= this.maxRestartsPerMinute) {
      console.error("[backend] restart limit reached; leaving backend offline");
      return;
    }

    this.restartTimestamps.push(now);
    const restartNumber = this.restartTimestamps.length;
    const delayMs = Math.min(4_000, 500 * 2 ** (restartNumber - 1));
    console.warn(`[backend] restarting in ${delayMs}ms`);
    this.restartTimer = setTimeout(() => {
      this.restartTimer = null;
      if (this.stopping) return;
      try {
        this.spawnBackend();
      } catch (error) {
        console.error("[backend] restart failed", error);
        this.scheduleRestart();
      }
    }, delayMs);
  }

  private async waitUntilReady(timeoutMs: number): Promise<boolean> {
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
    return {
      command: path.join(backendDir, "zml-game-bridge.exe"),
      args: ["serve", "--mode", "live"],
      cwd: backendDir,
    };
  }

  const backendDir = path.resolve(appRoot, "..", "game-bridge");
  const pythonExecutable =
    process.platform === "win32"
      ? path.join(backendDir, ".venv", "Scripts", "python.exe")
      : path.join(backendDir, ".venv", "bin", "python");
  return {
    command: pythonExecutable,
    args: ["-m", "zml_game_bridge.dev_cli", "serve", "--mode", "live"],
    cwd: backendDir,
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
    return ["1", "true", "yes", "on"].includes(explicitValue.trim().toLowerCase());
  }
  return !backendUrlOverridden;
}

async function checkBackendHealth(baseUrl: string): Promise<boolean> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), HEALTH_REQUEST_TIMEOUT_MS);
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
  if (/^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//.test(baseUrl)) return baseUrl;
  return `http://${baseUrl}`;
}

function forwardBackendOutput(child: ChildProcessWithoutNullStreams): void {
  child.stdout.on("data", (chunk: Buffer) => {
    const message = chunk.toString("utf8").trimEnd();
    if (message) console.info(`[backend] ${message}`);
  });
  child.stderr.on("data", (chunk: Buffer) => {
    const message = chunk.toString("utf8").trimEnd();
    if (message) console.error(`[backend] ${message}`);
  });
}

function waitForChildClose(
  child: ChildProcessWithoutNullStreams,
  timeoutMs: number,
): Promise<boolean> {
  if (child.exitCode !== null || child.signalCode !== null) return Promise.resolve(true);

  return new Promise((resolve) => {
    const onClose = () => {
      clearTimeout(timeout);
      resolve(true);
    };
    const timeout = setTimeout(() => {
      child.removeListener("close", onClose);
      resolve(false);
    }, timeoutMs);
    child.once("close", onClose);
  });
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
