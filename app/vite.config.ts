import { fileURLToPath, URL } from 'node:url'

import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    // Listen on every interface so phones and tablets on the same network can reach the
    // development server; the proxy below still talks to the API on the host itself.
    host: true,
    port: Number(process.env.MUNINN_WEB_PORT ?? 5173),
    proxy: {
      // The API runs in Docker; in development the app talks to it through this proxy so that
      // cookies and the same-origin rules behave like they do behind Caddy later.
      '/api': {
        // On the host that is the published port; in the development container the API is a
        // neighbour, reached by its name. MUNINN_API_URL says which.
        target: process.env.MUNINN_API_URL ?? 'http://127.0.0.1:8000',
        changeOrigin: true,
        // The live channel is a WebSocket under the same prefix.
        ws: true,
      },
    },
  },
  preview: {
    host: true,
    port: 4173,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: true,
  },
})
