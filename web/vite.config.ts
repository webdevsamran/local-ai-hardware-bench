/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Static deployment to GitHub Pages: base path is set at build time via
// --base=/local-ai-hardware-bench/ (see CI) or defaults to '/' for local dev.
export default defineConfig({
  plugins: [react()],
  base: process.env.VITE_BASE_PATH || '/',
  build: {
    sourcemap: true,
    chunkSizeWarningLimit: 500,
    // The prerenderer reads this to emit a <link rel="modulepreload"> for the
    // route chunk each page needs. Without it hydration discovers the chunk
    // only after the entry script has parsed, which is a request the browser
    // could have started at the same time as the entry.
    manifest: true,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['tests/**/*.test.{ts,tsx}'],
    setupFiles: ['tests/setup.ts'],
  },
})