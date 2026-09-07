import { expect, test } from '@playwright/test'

import { apiHeaders } from './apiKey'

/**
 * Django admin HITL approval, end to end (spec 051 / BL-20260503-17).
 *
 * `backend/tests/ingestion/` proves `approve_and_commit` calls the right
 * services, but the admin action itself — the changelist, the checkbox, the
 * action dropdown, the CSRF-protected POST — was only ever exercised by hand.
 * Approving in a real browser and then asking the *graph API* whether the case
 * arrived is the only check that covers the whole path
 * (admin → approval service → IngestionScout → Neo4j).
 *
 * The row comes from `manage.py seed_review_queue --reset`, which `make
 * test-e2e` runs against `backend-e2e` before the browser starts; the login
 * comes from `manage.py seed_admin` in that service's boot command. Extraction
 * is rule-based (eyecite), so no model is called and nothing is billed.
 */

const ADMIN_USER = process.env.E2E_ADMIN_USERNAME ?? 'e2e-admin'
const ADMIN_PASS = process.env.E2E_ADMIN_PASSWORD ?? 'e2e-admin-pass'

/** Ids seeded by law_ai/ingestionapp/management/commands/seed_review_queue.py. */
const REVIEW_ID = 'e2e-hitl-review'
const CASE_ID = 'e2e-hitl-case'

const ADMIN = 'http://localhost:8000/admin'
const CHANGELIST = `${ADMIN}/ingestionapp/pendingreview/`

test.describe.configure({ mode: 'serial' })

test('an admin logs in, approves a quarantined case, and it reaches the graph', async ({
  page,
  request,
}) => {
  // --- login ---------------------------------------------------------------
  await page.goto(`${ADMIN}/login/?next=/admin/`)
  await page.getByLabel('Username').fill(ADMIN_USER)
  await page.getByLabel('Password').fill(ADMIN_PASS)
  await page.getByRole('button', { name: /log in/i }).click()
  await expect(
    page.getByRole('heading', { name: /site administration/i }),
  ).toBeVisible()

  // --- the quarantine queue ------------------------------------------------
  await page.goto(CHANGELIST)
  const row = page.locator(`#result_list tr`, { hasText: REVIEW_ID })
  await expect(
    row,
    `no pending row ${REVIEW_ID} — run \`manage.py seed_review_queue --reset\``,
  ).toHaveCount(1)
  // Seeded uncommitted: the "committed at" column is the admin's own dash.
  await expect(row).toContainText('0.42')

  // --- approve + commit ----------------------------------------------------
  await row.locator('input[name="_selected_action"]').check()
  await page.selectOption('select[name="action"]', 'approve_and_commit')
  await page.getByRole('button', { name: /^go$/i }).click()

  // Django reports the outcome in its message list; the action commits
  // synchronously, so by the time the page settles the write has happened.
  const banner = page.locator('.messagelist')
  await expect(banner).toBeVisible({ timeout: 60_000 })
  await expect(banner, 'the admin reported a commit').toContainText(
    /1 committed to the graph/i,
  )

  // --- the row records the decision ---------------------------------------
  const committed = page.locator('#result_list tr', { hasText: REVIEW_ID })
  await expect(committed).not.toContainText('commit failed')

  // --- and the graph agrees ------------------------------------------------
  // Asserted through /api/graph, never by talking to Neo4j from the browser.
  await expect
    .poll(
      async () => {
        const res = await request.get(
          `http://localhost:8000/api/graph/neighborhood/${CASE_ID}`,
          { headers: apiHeaders() },
        )
        if (!res.ok()) return `HTTP ${res.status()}`
        const body = await res.json()
        if (body.available === false) return 'graph unavailable'
        // The graph API speaks Cytoscape: every element is `{ data: {...} }`.
        return (body.nodes ?? []).some(
          (n: { data?: { id?: string } }) => n.data?.id === CASE_ID,
        )
      },
      {
        message: `:Case ${CASE_ID} never appeared in the graph`,
        timeout: 30_000,
      },
    )
    .toBe(true)
})

test('approving an already-committed row is a no-op, not a second write', async ({
  page,
}) => {
  await page.goto(`${ADMIN}/login/?next=/admin/`)
  await page.getByLabel('Username').fill(ADMIN_USER)
  await page.getByLabel('Password').fill(ADMIN_PASS)
  await page.getByRole('button', { name: /log in/i }).click()

  await page.goto(CHANGELIST)
  const row = page.locator('#result_list tr', { hasText: REVIEW_ID })
  await row.locator('input[name="_selected_action"]').check()
  await page.selectOption('select[name="action"]', 'approve_and_commit')
  await page.getByRole('button', { name: /^go$/i }).click()

  // `commit_approved_review` short-circuits on `committed_at`, so the second
  // pass must report a skip rather than committing the same case twice.
  await expect(page.locator('.messagelist')).toContainText(
    /already committed \(skipped\)/i,
  )
})
