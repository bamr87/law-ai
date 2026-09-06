import { defineConfig, devices } from '@playwright/test'

/**
 * Browser end-to-end harness (spec 051 / BL-20260811-16).
 *
 * Runs ONLY through `make test-e2e`, which brings up the live compose stack
 * plus the `backend-e2e` sidecar (an API pinned to a deliberately unreachable
 * Ollama, so analysis runs are deterministic and bill nobody) and executes
 * this suite inside the official Playwright image on the compose network.
 *
 * The browser sees the stack the way a developer's does — `localhost:3000`
 * and `localhost:8000` — because `e2e/proxy.mjs` (our `webServer`) forwards
 * those loopback ports to `frontend:3000` / `backend-e2e:8000`. With the
 * E2E_*_UPSTREAM variables unset (a host developer, or CI with the ports
 * published) the forwarder is skipped and whatever answers on those ports is
 * used as-is.
 *
 * Deliberately NOT part of `make test`: a full-stack boot is minutes, so this
 * runs from the nightly workflow and on demand.
 */

const BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:3000'
const needsProxy = Boolean(
  process.env.E2E_FRONTEND_UPSTREAM || process.env.E2E_BACKEND_UPSTREAM,
)

export default defineConfig({
  testDir: './e2e',
  testMatch: /.*\.spec\.ts$/,
  // Serial by default: the specs share one backend, one Neo4j and one admin
  // login; a handful of specs is not worth the flake budget of parallelism.
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: 1,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: process.env.CI
    ? [['list'], ['html', { open: 'never', outputFolder: 'playwright-report' }]]
    : [['list']],
  outputDir: 'test-results',
  use: {
    baseURL: BASE_URL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'off',
    // Screenshots/traces should not depend on where an animation happened
    // to be (docs/ui-ux-review.md). `reducedMotion` is a browser-context
    // option, so it goes through contextOptions rather than `use` directly.
    contextOptions: { reducedMotion: 'reduce' },
    // The analysis spec asserts the trace-id copy control writes to the
    // clipboard; headless Chromium needs both grants for that.
    permissions: ['clipboard-read', 'clipboard-write'],
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: needsProxy
    ? {
        command: 'node e2e/proxy.mjs',
        url: `${BASE_URL}/`,
        reuseExistingServer: true,
        // Next dev compiles `/` on first request; a cold stack takes a while.
        timeout: 180_000,
        stdout: 'pipe',
        stderr: 'pipe',
      }
    : undefined,
})
