import react from '@vitejs/plugin-react'
import path from 'path'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    // The suite mocks the network at the backend's own origin (MSW handlers in
    // `mocks/server.ts` and in the per-test `server.use(...)` calls). The dev
    // container points the browser at the same-origin proxy instead
    // (`NEXT_PUBLIC_API_BASE_URL=/api/backend`, BL-20260430-07), and that
    // value would otherwise leak into the test process and match nothing. The
    // proxy route itself is covered by `__tests__/lib/backendProxy.test.ts`.
    env: { NEXT_PUBLIC_API_BASE_URL: 'http://localhost:8000' },
    // The default 5s leaves no room for an await that is itself allowed a few
    // seconds. Suites here render whole modules and drive MSW round trips
    // under parallel load, and a case that needs more than a second is slow,
    // not broken — the per-await timeouts are what say "this is a failure"
    // (BL-20260905-02). Raising this alone would not fix a flaky `waitFor`,
    // whose own 1s default fires first; it exists so a lengthened await has
    // somewhere to run.
    testTimeout: 15000,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      exclude: [
        'node_modules/',
        'app/**',
        'components/GraphViewer.tsx',
        'vitest.config.ts',
        '**/*.d.ts',
        '**/mocks/**',
      ],
      thresholds: {
        lines: 70,
        functions: 70,
        branches: 65,
        statements: 70,
      },
    },
    include: ['**/*.{test,spec}.{ts,tsx}'],
    exclude: ['node_modules', 'e2e', '.next'],
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './'),
    },
  },
})