import { spawn } from "node:child_process";

const viteCommand = process.platform === "win32" ? "vite.cmd" : "vite";

const child = spawn(viteCommand, process.argv.slice(2), {
  stdio: "inherit",
  shell: process.platform === "win32",
  env: {
    ...process.env,
    ZML_UI_MOCKS: "1",
  },
});

child.on("exit", (code) => {
  process.exit(code ?? 0);
});

child.on("error", (error) => {
  console.error(error);
  process.exit(1);
});
