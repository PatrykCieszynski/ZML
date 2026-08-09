import path from "node:path";
import { describe, expect, it } from "vitest";

import {
  createBackendLaunchSpec,
  shouldManageBackend,
} from "./backendProcessManager.ts";

describe("createBackendLaunchSpec", () => {
  it("uses the bundled executable in a packaged app", () => {
    const launch = createBackendLaunchSpec({
      isPackaged: true,
      resourcesPath: path.join("C:", "Z Mining Log", "resources"),
      appRoot: path.join("C:", "repo", "apps", "electron-ui"),
    });

    expect(launch.command).toBe(
      path.join(
        "C:",
        "Z Mining Log",
        "resources",
        "backend",
        "zml-game-bridge.exe",
      ),
    );
    expect(launch.args).toEqual(["serve", "--mode", "live"]);
    expect(launch.environment).toEqual({
      ZML_OCR_AGENT_PATH: path.join(
        "C:",
        "Z Mining Log",
        "resources",
        "ocr-agent",
        "zml-ocr-agent.exe",
      ),
    });
  });

  it("uses the workspace virtualenv in development", () => {
    const appRoot = path.join("C:", "repo", "apps", "electron-ui");
    const launch = createBackendLaunchSpec({
      isPackaged: false,
      resourcesPath: path.join("C:", "unused"),
      appRoot,
    });

    const repoRoot = path.resolve(appRoot, "..", "..");
    const workspaceVenv = path.join(repoRoot, ".venv");
    expect(launch.cwd).toBe(path.resolve(appRoot, "..", "game-bridge"));
    expect(launch.command).toBe(
      process.platform === "win32"
        ? path.join(workspaceVenv, "Scripts", "python.exe")
        : path.join(workspaceVenv, "bin", "python"),
    );
    expect(launch.args).toEqual([
      "-m",
      "zml_game_bridge.dev_cli",
      "serve",
      "--mode",
      "live",
    ]);
    expect(launch.environment).toEqual({
      ZML_OCR_AGENT_PATH:
        process.platform === "win32"
          ? path.join(workspaceVenv, "Scripts", "zml-ocr-agent.exe")
          : path.join(workspaceVenv, "bin", "zml-ocr-agent"),
    });
  });
});

describe("shouldManageBackend", () => {
  it("manages the default local backend", () => {
    expect(
      shouldManageBackend({
        mocksEnabled: false,
        backendUrlOverridden: false,
        explicitValue: undefined,
      }),
    ).toBe(true);
  });

  it("does not manage mocks or an explicitly configured backend", () => {
    expect(
      shouldManageBackend({
        mocksEnabled: true,
        backendUrlOverridden: false,
        explicitValue: undefined,
      }),
    ).toBe(false);
    expect(
      shouldManageBackend({
        mocksEnabled: false,
        backendUrlOverridden: true,
        explicitValue: undefined,
      }),
    ).toBe(false);
  });

  it("allows an explicit lifecycle override", () => {
    expect(
      shouldManageBackend({
        mocksEnabled: false,
        backendUrlOverridden: true,
        explicitValue: "true",
      }),
    ).toBe(true);
    expect(
      shouldManageBackend({
        mocksEnabled: false,
        backendUrlOverridden: false,
        explicitValue: "false",
      }),
    ).toBe(false);
  });
});
