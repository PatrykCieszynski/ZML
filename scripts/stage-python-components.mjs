import { access, cp, mkdir, rm } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const components = [
  {
    name: "Game Bridge",
    source: path.join(
      repoRoot,
      "apps",
      "game-bridge",
      "dist",
      "zml-game-bridge",
    ),
    executable: "zml-game-bridge.exe",
    target: path.join(repoRoot, "apps", "electron-ui", "resources", "backend"),
  },
  {
    name: "OCR Agent",
    source: path.join(repoRoot, "apps", "ocr-agent", "dist", "zml-ocr-agent"),
    executable: "zml-ocr-agent.exe",
    target: path.join(
      repoRoot,
      "apps",
      "electron-ui",
      "resources",
      "ocr-agent",
    ),
  },
];

for (const component of components) {
  try {
    await access(path.join(component.source, component.executable));
  } catch {
    throw new Error(
      `${component.name} package was not found at ${component.source}. Run both Python package steps first.`,
    );
  }
}

for (const component of components) {
  await rm(component.target, { recursive: true, force: true });
  await mkdir(path.dirname(component.target), { recursive: true });
  await cp(component.source, component.target, { recursive: true });
  console.info(
    `Staged ${component.name}: ${component.source} -> ${component.target}`,
  );
}
