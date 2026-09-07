import { expect, test, type Page } from '@playwright/test'

import { apiHeaders } from './apiKey'

/**
 * Route smoke (spec 051 / BL-20260811-16): every module in the catalog
 * renders against the live stack with no failed API call. This is the
 * canary for the harness itself — if the forwarder, the sidecar or Next dev
 * is broken, this fails first and cheapest.
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

const ROUTES: { path: string; heading: RegExp }[] = [
  { path: '/', heading: /dashboard|law ai/i },
  { path: '/agents', heading: /agent/i },
  { path: '/analysis', heading: /analysis/i },
  { path: '/graph', heading: /graph/i },
  { path: '/lsat', heading: /lsat/i },
  { path: '/settings', heading: /settings/i },
]

for (const route of ROUTES) {
  test(`${route.path} renders with a healthy API`, async ({ page }) => {
    const failures: string[] = []
    page.on('response', (res) => {
      if (res.url().includes('/api/') && res.status() >= 400) {
        failures.push(`${res.status()} ${res.url()}`)
      }
    })

    await page.goto(route.path)
    await expect(page.getByRole('main')).toBeVisible()
    await expect(
      page.getByRole('heading', { level: 1, name: route.heading }),
    ).toBeVisible()
    // The shell's primary navigation is the one landmark every route shares.
    await expect(page.getByTestId('nav-rail')).toBeVisible()
    // Let in-flight data fetches settle before judging them.
    await settleNetwork(page)
    expect(failures, 'API responses ≥ 400').toEqual([])
  })
}

test('both routes into the API reach the e2e sidecar, not the dev backend', async ({
  page,
  request,
}) => {
  // Two paths reach the API now: the browser's REST calls go through the Next
  // same-origin proxy (BL-20260430-07), and the agent socket goes to :8000
  // directly. Both must land on `backend-e2e` — it is the only one pinned to
  // an unreachable Ollama, and that pin is what keeps a nightly run from
  // calling the operator's real provider chain.
  const isSidecar = (body: {
    ollama?: { reachable?: boolean }
    llm_chain?: { provider?: string }[]
  }) =>
    body.ollama?.reachable === false &&
    (body.llm_chain ?? []).map((t) => t.provider).join(',') === 'ollama'

  const direct = await request.get(
    'http://localhost:8000/api/agents/health/local-ai',
    { headers: apiHeaders() },
  )
  expect(direct.ok()).toBe(true)
  expect(isSidecar(await direct.json()), 'direct :8000 is the sidecar').toBe(true)

  await page.goto('/')
  const proxied = await page.evaluate(async () => {
    const res = await fetch('/api/backend/api/agents/health/local-ai')
    return res.json()
  })
  expect(isSidecar(proxied), 'the same-origin proxy points at the sidecar').toBe(
    true,
  )
})

test('the health endpoint answers', async ({ request }) => {
  const res = await request.get('http://localhost:8000/health')
  expect(res.ok()).toBe(true)
  expect(await res.json()).toMatchObject({ status: 'healthy' })
})
