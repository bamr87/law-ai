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
    // Matches frontend/vitest.config.ts. The default 5s is not a statement
    // about correctness, and every one of these files mounts a whole view: on
    // a loaded machine a case that takes six seconds is slow, not broken, and
    // failing it teaches the suite to be distrusted.
    testTimeout: 15000,
    include: ['**/*.{test,spec}.{ts,tsx}'],
    // `e2e/` is Playwright's: its specs match the same glob but need a real
    // browser and Playwright's own `test`/`expect`, so vitest must not collect
    // them.
    exclude: ['node_modules', 'out', '.next', 'e2e'],
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './'),
    },
  },
})
