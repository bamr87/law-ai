// Component-test runner for the static LSAT site (BL-20260831-18).
//
// Mirrors frontend/vitest.config.ts so the two products are tested the same
// way: jsdom, RTL, the `@/` alias the source already uses. There is no MSW
// here because the site has no network — everything comes from content.json,
// and tests that need a smaller bundle mock that module instead.
import react from '@vitejs/plugin-react'
import path from 'path'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    include: ['**/*.{test,spec}.{ts,tsx}'],
    exclude: ['node_modules', 'out', '.next'],
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './'),
    },
  },
})
