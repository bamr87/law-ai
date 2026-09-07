import { defineConfig, devices } from '@playwright/test'

/**
 * Viewport measurement harness for the static LSAT site (spec 051 /
 * BL-20260901-03).
 *
 * The responsive numbers in specs/047 (header 136px → 85px at 390px, 60px
 * condensed, sticky passage column at 1280px) were measured by driving a
 * browser by hand. A jsdom runner cannot reproduce them — it has no layout —
 * so this runs the real export in a real browser.
 *
 * Entry point is `make lsat-static-e2e`, which builds `out/` and then runs
 * this suite inside the pinned Playwright image. `e2e/serve.mjs` is the
 * webServer; it serves the export under the same base path Pages uses.
 *
 * NOTE: lsat-static/package.json declares no `"type": "module"`, so this file
 * loads as CommonJS — no `import.meta.url` here (paths come from cwd).
 */

const PORT = Number(process.env.E2E_PORT ?? 4321)
const RAW_BASE = process.env.PAGES_BASE_PATH ?? '/law-ai'
const BASE_PATH = RAW_BASE === '/' ? '' : RAW_BASE.replace(/\/$/, '')

export default defineConfig({
  testDir: './e2e',
  testMatch: /.*\.spec\.ts$/,
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: 1,
  timeout: 45_000,
  expect: { timeout: 10_000 },
  reporter: [['list']],
  outputDir: 'test-results',
  use: {
    baseURL: `http://127.0.0.1:${PORT}${BASE_PATH}/`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    // Layout measurements must not depend on where an entrance animation
    // happened to be. `reducedMotion` is a browser-context option in
    // Playwright 1.59, so it goes through contextOptions.
    contextOptions: { reducedMotion: 'reduce' },
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: 'node e2e/serve.mjs',
    url: `http://127.0.0.1:${PORT}${BASE_PATH}/`,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
    stdout: 'pipe',
    stderr: 'pipe',
  },
})
