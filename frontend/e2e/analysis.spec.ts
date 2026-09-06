import { expect, test } from '@playwright/test'

/**
 * Analysis Studio smoke (spec 051 / BL-20260429-27): form fill → result render
 * → trace-id copy, against the live Docker stack.
 *
 * Two halves, because one stack cannot honestly produce both:
 *
 * 1. A *live* run. The `backend-e2e` sidecar points at an unreachable Ollama,
 *    so `POST /api/analysis` takes the honest degraded path — a real request,
 *    a real response, a real render, and no model bill. What renders there is
 *    the engine-state panel, and that is what this spec asserts; the healthy
 *    branch (IRAC card, precedents, trace-id chip) does not exist on it.
 * 2. A *persisted* run, replayed at `/analysis?id=…`. `make test-e2e` seeds it
 *    with `manage.py seed_analysis_run`, so the healthy branch renders through
 *    the same proxy, the same gated router and the same `ResultPanel` a paid
 *    run would use — which is where the IRAC brief, the precedent list and the
 *    trace-id copy control actually live.
 */

const FACTS =
  'A city ordinance bans door-to-door canvassing without a permit. ' +
  'A political group sues on First Amendment grounds.'

/** Matches `seed_analysis_run.ANALYSIS_ID` / `TRACE_ID`. */
const SEEDED_ID = 'an-e2e-demo'
const SEEDED_TRACE_ID = 'e2e-trace-0123456789abcdef'

test('fills the form and renders the engine state the stack really produced', async ({
  page,
}) => {
  await page.goto('/analysis')

  const textarea = page.getByLabel('Fact pattern')
  await expect(textarea).toBeVisible()
  await textarea.fill(FACTS)
  await page.getByLabel('Jurisdiction').selectOption('US')

  const run = page.getByRole('button', { name: /run analysis/i })
  await expect(run).toBeEnabled()
  const [response] = await Promise.all([
    page.waitForResponse(
      (res) =>
        res.url().includes('/api/analysis') && res.request().method() === 'POST',
      { timeout: 60_000 },
    ),
    run.click(),
  ])
  expect(response.status(), 'the sidecar answered the run').toBeLessThan(400)

  // --- result render -------------------------------------------------------
  // No engine behind the sidecar ⇒ the engine-state panel, never an IRAC card
  // dressed up as an answer (BL-20260810-16).
  const engineState = page.getByTestId('engine-state')
  await expect(engineState).toBeVisible({ timeout: 60_000 })
  await expect(
    page.getByRole('heading', { name: /no analysis produced/i }),
  ).toBeVisible()
  await expect(page.getByRole('region', { name: /irac brief/i })).toHaveCount(0)
  // The run is still addressable, which is the permalink half of the render.
  await expect(page.locator('a[href^="/analysis?id=an-"]')).toBeVisible()
})

test('replays a persisted run: IRAC, precedents, and the trace-id copy', async ({
  page,
  context,
}) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await page.goto(`/analysis?id=${SEEDED_ID}`)

  // The stored request comes back into the form alongside the result.
  await expect(page.getByLabel('Fact pattern')).not.toHaveValue('')

  const irac = page.getByRole('region', { name: /irac brief/i })
  await expect(irac).toBeVisible({ timeout: 30_000 })
  for (const field of ['Issue', 'Rule', 'Application', 'Conclusion']) {
    // `<dt>`/`<dd>` — Chromium exposes no accessible name for a term, so the
    // label is matched as text and the value must be non-empty beside it.
    const term = irac.locator('dt', { hasText: new RegExp(`^${field}$`, 'i') })
    await expect(term, field).toBeVisible()
    await expect(term.locator('+ dd'), `${field} value`).not.toBeEmpty()
  }
  await expect(page.getByRole('region', { name: /precedent/i })).toBeVisible()

  // --- trace id copy -------------------------------------------------------
  const chip = page.getByTestId('trace-id')
  await expect(chip).toBeVisible()
  const copy = page.getByRole('button', { name: /^copy trace id/i })
  const fullTraceId = (await copy.getAttribute('aria-label'))!.replace(
    /^Copy trace id /,
    '',
  )
  expect(fullTraceId).toBe(SEEDED_TRACE_ID)
  // The chip elides; the clipboard must carry the whole id.
  await expect(chip).not.toHaveText(fullTraceId)

  await copy.click()
  await expect(copy).toHaveText('Copied')
  const clipboard = await page.evaluate(() => navigator.clipboard.readText())
  expect(clipboard).toBe(fullTraceId)
})

test('an empty fact pattern cannot be submitted', async ({ page }) => {
  await page.goto('/analysis')
  await expect(page.getByRole('button', { name: /run analysis/i })).toBeDisabled()
})

test('the sample loader fills the form and enables the run', async ({
  page,
}) => {
  await page.goto('/analysis')
  await page.getByRole('button', { name: 'Load sample' }).click()
  await expect(page.getByLabel('Fact pattern')).not.toHaveValue('')
  await expect(page.getByRole('button', { name: /run analysis/i })).toBeEnabled()
})
