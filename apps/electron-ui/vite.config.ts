/// <reference types="vitest" />
/// <reference types="vite/client" />
import { defineConfig } from 'vite'
import path from 'node:path'
import electron from 'vite-plugin-electron/simple'
import react from '@vitejs/plugin-react'

const sharedIndex = path.resolve(__dirname, "shared/index.ts");

// https://vitejs.dev/config/
export default defineConfig(() => {
  return {
    resolve: {
      alias: {
        "@zml/shared": sharedIndex,
      },
    },
    plugins: [
      react(),
      electron({
        main: {
          entry: 'electron/main.ts',
          vite: {
            resolve: {
              alias: {
                "@zml/shared": sharedIndex,
              },
            },
          },
        },
        preload: {
          input: path.join(__dirname, 'electron/preload.ts'),
          vite: {
            resolve: {
              alias: {
                "@zml/shared": sharedIndex,
              },
            },
          },
        },

      }),
    ],
    build: {
      rollupOptions: {
        input: {
          main: path.resolve(__dirname, 'index.html'),
        },
      },
    },
  }
})
