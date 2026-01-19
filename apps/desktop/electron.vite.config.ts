import { defineConfig } from "electron-vite";
import path from "node:path";

const repoRoot = path.resolve(__dirname, "../..");
const uiRoot = path.resolve(repoRoot, "apps/ui");
const sharedIndex = path.resolve(repoRoot, "packages/shared/src/index.ts");

export default defineConfig({
    main: {
        resolve: {
            alias: {
                "@zml/shared": sharedIndex,
            },
        },
        build: {
            outDir: "dist/main",
            lib: {
                entry: path.resolve(__dirname, "src/main.ts"),
            },
        },
    },

    preload: {
        resolve: {
            alias: {
                "@zml/shared": sharedIndex,
            },
        },
        build: {
            outDir: "dist/preload",
            lib: {
                entry: path.resolve(__dirname, "src/preload.ts"),
            },
            // Required for sandboxed preload: bundle deps instead of externalizing them.
            externalizeDeps: false,
            rollupOptions: {
                output: {
                    // Keep preload as a single file (avoid chunking).
                    inlineDynamicImports: true,
                },
            },
        },
    },

    renderer: {
        root: uiRoot,
        resolve: {
            alias: {
                "@zml/shared": sharedIndex,
            },
        },
        build: {
            outDir: path.resolve(__dirname, "dist/renderer"),
            emptyOutDir: true,
            rollupOptions: {
                input: path.resolve(uiRoot, "index.html"),
            },
        },
    },
});
