import { access, cp, mkdir, rm } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);
const components = [
  {
    name: "Backend",
    source: path.join(
      repoRoot,
      "apps",
      "backend",
      "dist",
      "zml-backend",
    ),
    executable: "zml-backend.exe",
    target: path.join(repoRoot, "apps", "desktop", "resources", "backend"),
  },
  {
    name: "OCR Worker",
    source: path.join(repoRoot, "apps", "ocr-worker", "dist", "zml-ocr-worker"),
    executable: "zml-ocr-worker.exe",
    target: path.join(
      repoRoot,
      "apps",
      "desktop",
      "resources",
      "ocr-worker",
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
