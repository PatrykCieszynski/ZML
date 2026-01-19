import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  base: "./",
  plugins: [react()],
  resolve: {
    alias: {
      "@zml/shared": path.resolve(__dirname, "../../packages/shared/src/index.ts"),
    },
  },
});
