import { expect, test, type Page } from '@playwright/test'

/**
 * API-key gating across all four feature pages (spec 051 / BL-20260430-11).
 *
 * The backend's key check is env-driven (`law_ai/core/auth.py` resolves
 * `AGENT_API_KEY` with per-router overrides), so the only honest way to test it
 * is to run the stack both ways. `backend-e2e` takes its key from
 * `E2E_AGENT_API_KEY`, and the same value reaches this spec:
 *
 *   make test-e2e                              # ungated — the first describe
 *   make test-e2e E2E_AGENT_API_KEY=s3cret     # gated  — the second
 *
 * `NEXT_PUBLIC_AGENT_API_KEY` is gone (BL-20260430-07): anything `NEXT_PUBLIC_*`
 * is compiled into the bundle, so the shared key was readable by anyone who
 * opened it. The browser now calls a same-origin proxy and the Next server
 * attaches a server-only `AGENT_API_KEY` — which `make test-e2e` sets from the
 * same `E2E_AGENT_API_KEY`. So the gated project checks three things: the
 * routers refuse a missing or wrong key, the pages still work through the
 * proxy, and the key never appears in anything the browser can read.
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

const KEY = process.env.E2E_AGENT_API_KEY ?? ''

/** Seeded by `manage.py seed_analysis_run` in `make test-e2e`. */
const SEEDED_ANALYSIS_ID = 'an-e2e-demo'

/**
 * The four feature pages named in the item, with their <h1> and the gated
 * router each one must actually reach.
 *
 * `served` is not decoration. A bare `/analysis` visit calls nothing behind
 * the analysis scope — AnalysisStudio only fetches on load when `?id=` is
 * present — so "the page loaded with no 401" was true there whether or not the
 * proxy attached a key. Naming the endpoint each page has to have called
 * successfully turns that vacuous assertion into a real one.
 */
const PAGES = [
  { path: '/agents', heading: /agent/i, served: /\/api\/agents\b/ },
  {
    path: `/analysis?id=${SEEDED_ANALYSIS_ID}`,
    heading: /analysis/i,
    served: /\/api\/analysis\//,
  },
  { path: '/graph', heading: /graph/i, served: /\/api\/graph\// },
  { path: '/lsat', heading: /lsat/i, served: /\/api\/lsat\// },
]

/**
 * A 401 that is the correct answer, not a misconfigured gate.
 *
 * `/api/matters` is account-scoped (spec 036): the shell asks for the signed-in
 * user's matters on every page, and an anonymous browser is *supposed* to be
 * refused. Counting it as a denial would make "no 401 anywhere" unsatisfiable
 * on both postures.
 */
const ANONYMOUS_BY_DESIGN = /\/api\/matters\b/

/**
 * How long a page gets to reach its router.
 *
 * Generous on purpose: the stack runs `next dev`, which compiles the
 * `/api/backend/[...path]` proxy route on its first request. A `networkidle`
 * wait can easily settle before that compile finishes, which is exactly how
 * the earlier version of this spec ended up asserting "no 401" over a page
 * that had made no request at all.
 */
const SERVED_TIMEOUT_MS = 30_000

/**
 * One cheap GET behind each router's own scope — all four scopes
 * `law_ai/core/auth.py` defines, including `RequireAnalysis`, whose
 * `ANALYSIS_API_KEY`/`AGENT_API_KEY` fallback was previously untested.
 */
const ENDPOINTS = [
  'http://localhost:8000/api/agents/',
  `http://localhost:8000/api/analysis/${SEEDED_ANALYSIS_ID}`,
  'http://localhost:8000/api/graph/stats',
  'http://localhost:8000/api/lsat/sections',
]

/** Record every `/api/` response the page provoked. */
function watchApi(page: Page): {
  statuses: number[]
  denied: string[]
  served: string[]
} {
  const seen = {
    statuses: [] as number[],
    denied: [] as string[],
    served: [] as string[],
  }
  page.on('response', (res) => {
    if (!res.url().includes('/api/')) return
    seen.statuses.push(res.status())
    if (res.status() === 401 || res.status() === 403) {
      if (ANONYMOUS_BY_DESIGN.test(res.url())) return
      seen.denied.push(`${res.status()} ${res.url()}`)
    } else if (res.status() < 400) {
      seen.served.push(res.url())
    }
  })
  return seen
}

/** The page really reached its own router, and was served. */
async function expectReachedItsRouter(
  seen: { served: string[] },
  path: string,
  served: RegExp,
): Promise<void> {
  await expect
    .poll(() => seen.served.filter((url) => served.test(url)).length, {
      timeout: SERVED_TIMEOUT_MS,
      message:
        `${path} must actually be served by ${served} — otherwise "no 401" ` +
        `proves nothing about the gate. Saw: ` +
        `${seen.served.join(', ') || '(no successful /api/ response)'}`,
    })
    .toBeGreaterThan(0)
}

async function expectPageRenders(page: Page, heading: RegExp): Promise<void> {
  await expect(page.getByRole('main')).toBeVisible()
  await expect(
    page.getByRole('heading', { level: 1, name: heading }),
  ).toBeVisible()
  await settleNetwork(page)
}

test.describe('AGENT_API_KEY unset', () => {
  test.skip(
    Boolean(KEY),
    'the stack is gated — this project needs E2E_AGENT_API_KEY empty',
  )

  for (const { path, heading, served } of PAGES) {
    test(`${path} loads with no denied API call`, async ({ page }) => {
      const seen = watchApi(page)
      await page.goto(path)
      await expectPageRenders(page, heading)
      await expectReachedItsRouter(seen, path, served)
      expect(seen.denied, 'no 401/403 on an ungated stack').toEqual([])
    })
  }

  test('the routers answer an unauthenticated request', async ({ request }) => {
    for (const url of ENDPOINTS) {
      const res = await request.get(url)
      expect(res.status(), url).toBeLessThan(400)
    }
  })
})

test.describe('AGENT_API_KEY set', () => {
  test.skip(
    !KEY,
    'run `make test-e2e E2E_AGENT_API_KEY=…` to exercise the gate',
  )

  test('every router rejects a missing or wrong key', async ({ request }) => {
    for (const url of ENDPOINTS) {
      const anonymous = await request.get(url)
      expect([401, 403], `${url} without a key`).toContain(anonymous.status())

      const wrong = await request.get(url, {
        headers: { 'X-API-Key': `${KEY}-wrong` },
      })
      expect([401, 403], `${url} with a wrong key`).toContain(wrong.status())

      const right = await request.get(url, { headers: { 'X-API-Key': KEY } })
      expect(right.status(), `${url} with the right key`).toBeLessThan(400)
    }
  })

  for (const { path, heading, served } of PAGES) {
    test(`${path} loads end-to-end through the proxy`, async ({ page }) => {
      const seen = watchApi(page)
      await page.goto(path)
      await expectPageRenders(page, heading)
      // Order matters: without a served call first, "the proxy attached the
      // key" would pass on a page that called nothing at all.
      await expectReachedItsRouter(seen, path, served)
      expect(seen.denied, 'the proxy attached the key').toEqual([])
    })
  }

  test('the browser cannot set the key for itself', async ({ page }) => {
    // The proxy strips an inbound X-API-Key and supplies its own, so a page
    // that forges the header gains nothing — and a page that omits it loses
    // nothing. Both must succeed, and identically.
    await page.goto('/')
    const statuses = await page.evaluate(async (key) => {
      const plain = await fetch('/api/backend/api/agents/')
      const forged = await fetch('/api/backend/api/agents/', {
        headers: { 'X-API-Key': `${key}-forged` },
      })
      return [plain.status, forged.status]
    }, KEY)
    expect(statuses[0]).toBeLessThan(400)
    expect(statuses[1], 'a forged header is stripped, not honoured').toBe(
      statuses[0],
    )
  })

  test('the key never reaches anything the browser can read', async ({
    page,
  }) => {
    const bodies: string[] = []
    page.on('response', async (res) => {
      const type = res.headers()['content-type'] ?? ''
      if (!/javascript|html/.test(type)) return
      bodies.push(await res.text().catch(() => ''))
    })
    await page.goto('/analysis')
    await settleNetwork(page)

    const leaked = bodies.filter((b) => b.includes(KEY))
    expect(leaked.length, 'the API key is not in the bundle').toBe(0)
    const inlined = await page.evaluate(
      () => JSON.stringify((globalThis as Record<string, unknown>).__NEXT_DATA__ ?? null),
    )
    expect(inlined).not.toContain(KEY)
  })
})
