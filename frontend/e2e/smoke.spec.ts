import { expect, test } from '@playwright/test'

/**
 * Route smoke (spec 051 / BL-20260811-16): every module in the catalog
 * renders against the live stack with no failed API call. This is the
 * canary for the harness itself — if the forwarder, the sidecar or Next dev
 * is broken, this fails first and cheapest.
 */

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
    await page.waitForLoadState('networkidle')
    expect(failures, 'API responses ≥ 400').toEqual([])
  })
}

test('the backend the browser talks to is the e2e sidecar', async ({
  request,
}) => {
  const res = await request.get('http://localhost:8000/health')
  expect(res.ok()).toBe(true)
  expect(await res.json()).toMatchObject({ status: 'healthy' })
})
