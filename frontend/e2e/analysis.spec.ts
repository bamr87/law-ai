import { expect, test } from '@playwright/test'

/**
 * Analysis Studio smoke (spec 051 / BL-20260429-27): form fill → result render
 * → trace-id copy, against the live Docker stack.
 *
 * The stack's `backend-e2e` sidecar points at an unreachable Ollama, so the
 * run takes `/api/analysis`'s honest degraded path (analysis/urls.py) — a real
 * request, a real response, a real render, and no model bill. The spec asserts
 * the shape of the result, not its prose, so it stays true whichever tier
 * answers.
 */

const FACTS =
  'A city ordinance bans door-to-door canvassing without a permit. ' +
  'A political group sues on First Amendment grounds.'

test('fills the form, renders a result, and copies the trace id', async ({
  page,
  context,
}) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await page.goto('/analysis')

  const textarea = page.getByLabel('Fact pattern')
  await expect(textarea).toBeVisible()
  await textarea.fill(FACTS)
  await page.getByLabel('Jurisdiction').selectOption('US')

  const run = page.getByRole('button', { name: /run analysis/i })
  await expect(run).toBeEnabled()
  await run.click()

  // --- result render -------------------------------------------------------
  const irac = page.getByRole('region', { name: /irac brief/i })
  await expect(irac).toBeVisible({ timeout: 60_000 })
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
  // The chip elides; the clipboard must carry the whole id.
  expect(fullTraceId.length).toBeGreaterThan(8)

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
