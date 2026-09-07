import { expect, test, type Page } from '@playwright/test'

/**
 * The browser talks to one origin — its own (spec 051 / BL-20260905-26).
 *
 * Since BL-20260430-07 the pages call `/api/backend/...` and the Next server
 * forwards, so the shared API key never reaches the bundle. Two layers already
 * cover pieces of that: `frontend/__tests__/lib/backendProxy.test.ts` drives
 * the route handler with a stubbed fetch, and the vitest env pins
 * `NEXT_PUBLIC_API_BASE_URL` back at the backend origin — so nothing in that
 * suite can notice a component that hard-codes `http://localhost:8000`. Only a
 * real browser can, and that is what this spec watches for.
 *
 * `/agents/reviews` earns its own case here (BL-20260906-05): the approve →
 * commit path is covered by RTL against MSW and by Django test-client tests,
 * but the page itself — its nav registration and its trip through the proxy —
 * was exercised by nobody.
 */

/**
 * Wait for the network to go quiet, but never longer than a few seconds.
 *
 * `/agents` polls every 5s (AgentDashboard `POLL_MS`), so a plain
 * `networkidle` can outlast the test timeout on a busy dev server. The wait is
 * an optimisation, not a precondition — time it out and carry on.
 */
async function settleNetwork(page: Page): Promise<void> {
  await page.waitForLoadState('networkidle', { timeout: 5_000 }).catch(() => {})
}

/**
 * The app's own origin. Not hard-coded: `baseURL` is what the runner was
 * pointed at, and a same-origin assertion has to mean "the page's origin".
 */
function origin(page: Page): string {
  return new URL(page.url()).origin
}

/**
 * Pages that fetch on load, so "it made no cross-origin call" is not vacuous.
 *
 * `?poll=off` freezes the dashboard's 5s heartbeat after its first pass
 * (BL-20260905-23) — the first pass is the part under test.
 */
const ROUTES = [
  '/agents?poll=off',
  '/agents/reviews',
  '/graph',
  '/lsat',
] as const

/** Every request the page made to an API path, whatever the origin. */
function watchApiRequests(page: Page): string[] {
  const urls: string[] = []
  page.on('request', (req) => {
    const url = req.url()
    if (!/\/api\//.test(url)) return
    urls.push(url)
  })
  return urls
}

for (const route of ROUTES) {
  test(`${route} reaches the backend only through its own origin`, async ({
    page,
  }) => {
    const urls = watchApiRequests(page)
    await page.goto(route)
    await expect(page.getByRole('main')).toBeVisible()
    await settleNetwork(page)

    // The page has to have called *something*, or "no cross-origin call" is
    // true of a screen that made no call at all.
    await expect
      .poll(() => urls.length, {
        timeout: 30_000,
        message: `${route} made no /api/ request; the assertion below would be vacuous`,
      })
      .toBeGreaterThan(0)

    const own = origin(page)
    const foreign = urls.filter((url) => !url.startsWith(own))
    expect(
      foreign,
      `${route} must call the backend through the same-origin proxy; a direct ` +
        'API origin in the browser is how the shared key ended up in the bundle',
    ).toEqual([])
    // Same-origin is necessary but not sufficient: `/api/backend/...` is the
    // proxy route, `/api/ws-ticket` is the app's own ticket minter, and there
    // is no third same-origin API surface.
    const unexpected = urls.filter(
      (url) =>
        !url.startsWith(`${own}/api/backend/`) &&
        !url.startsWith(`${own}/api/ws-ticket`),
    )
    expect(unexpected, 'every API call goes through a known app route').toEqual(
      [],
    )
  })
}

test('the review queue is registered in the shell nav and renders', async ({
  page,
}) => {
  await page.goto('/agents?poll=off')
  await expect(page.getByRole('main')).toBeVisible()

  // Registration, not a hand-typed URL: a module whose sidebar entry is
  // dropped is unreachable however well the page itself works.
  const link = page.getByRole('link', { name: /review queue/i }).first()
  await expect(link).toBeVisible()
  await link.click()

  await expect(page).toHaveURL(/\/agents\/reviews/)
  await expect(
    page.getByRole('heading', { level: 1, name: /quarantine review queue/i }),
  ).toBeVisible()
  // The status tabs come from the component, not the API, so they prove the
  // page mounted even on an empty queue.
  for (const label of ['Pending', 'Committed', 'Rejected']) {
    await expect(page.getByRole('button', { name: label })).toBeVisible()
  }
})

test('the review queue is served, not denied, through the proxy', async ({
  page,
}) => {
  const denied: string[] = []
  const served: string[] = []
  page.on('response', (res) => {
    if (!res.url().includes('/api/backend/api/ingestion/reviews')) return
    if (res.status() >= 400) denied.push(`${res.status()} ${res.url()}`)
    else served.push(res.url())
  })

  await page.goto('/agents/reviews')
  await expect(page.getByRole('main')).toBeVisible()

  await expect
    .poll(() => served.length, {
      timeout: 30_000,
      message: 'the review queue never reached /api/ingestion/reviews',
    })
    .toBeGreaterThan(0)
  expect(denied, 'the proxy attached whatever credential the stack needs').toEqual(
    [],
  )
})
