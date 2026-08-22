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
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['tests/**/*.test.{ts,tsx}'],
    setupFiles: ['tests/setup.ts'],
  },
})