import { access, cp, mkdir, rm } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = path.join(repoRoot, "apps", "game-bridge", "dist", "zml-game-bridge");
const target = path.join(repoRoot, "apps", "electron-ui", "resources", "backend");

try {
  await access(path.join(source, "zml-game-bridge.exe"));
} catch {
  throw new Error(
    `Packaged backend was not found at ${source}. Run the bridge package step first.`,
  );
}

await rm(target, { recursive: true, force: true });
await mkdir(path.dirname(target), { recursive: true });
await cp(source, target, { recursive: true });

console.info(`Staged backend: ${source} -> ${target}`);
