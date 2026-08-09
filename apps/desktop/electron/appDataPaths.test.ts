import path from "node:path";
import { describe, expect, it } from "vitest";

import { resolveDevelopmentAppDataPaths } from "./appDataPaths";

describe("resolveDevelopmentAppDataPaths", () => {
  it("keeps backend and Electron development state inside the workspace", () => {
    const workspaceRoot = path.resolve("repo");
    const electronUiRoot = path.join(workspaceRoot, "apps", "desktop");

    expect(resolveDevelopmentAppDataPaths(electronUiRoot)).toEqual({
      root: path.join(workspaceRoot, ".tmp", "appdata"),
      backend: path.join(workspaceRoot, ".tmp", "appdata", "backend"),
      electron: path.join(workspaceRoot, ".tmp", "appdata", "electron"),
    });
  });
});
