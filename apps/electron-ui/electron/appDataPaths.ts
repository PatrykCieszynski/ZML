import path from "node:path";

export type DevelopmentAppDataPaths = {
  root: string;
  backend: string;
  electron: string;
};

export function resolveDevelopmentAppDataPaths(
  electronUiRoot: string,
): DevelopmentAppDataPaths {
  const root = path.resolve(electronUiRoot, "..", "..", ".tmp", "appdata");

  return {
    root,
    backend: path.join(root, "backend"),
    electron: path.join(root, "electron"),
  };
}
