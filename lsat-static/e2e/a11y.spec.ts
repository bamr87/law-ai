import path from 'node:path'
import { expect, test, type Page } from '@playwright/test'

/**
 * Accessibility gate for the static site (#222).
 *
 * An axe-core WCAG 2.2 AA scan of the export found four rules failing on
 * views every student opens — the LR/RC/LG nav and the Library's Concepts tab
 * named by something other than their visible text, two scroll regions a
 * keyboard could not reach, no `<h1>`, and the footer row outside every
 * landmark — and nothing gated any of them: `scripts/ux_audit.py` greps
 * source, and the Vitest suite runs in jsdom, which computes no names from
 * layout and no overflow at all. This sweeps every top-level destination at
 * the two viewports the report used, in the browser that ships, over the same
 * built export Pages publishes, so a regression fails `make lsat-static-e2e`
 * and the deploy job rather than reaching the site.
 *
 * The gate is every WCAG 2.0/2.1/2.2 A and AA rule plus the two best-practice
 * rules #222 named (`page-has-heading-one`, `region`). Other best-practice
 * rules are reported in the failure message but do not fail the run: axe adds
 * and retunes them between minor releases, and `axe-core` rides `^4`, so
 * gating on them would let a dependency bump block a deploy.
 *
 * axe-core is injected from node_modules, the way frontend/e2e/a11y.spec.ts
 * does it, rather than through `@axe-core/playwright`: the wrapper only adds a
 * dependency for `page.evaluate(axe.run)`. axe-core is MPL-2.0, a dev-only
 * test dependency that never enters the export (constitution §8).
 *
 * Paths come from the runner's cwd (`lsat-static/` in the e2e image): this
 * package declares no `"type": "module"`, so the spec loads as CommonJS.
 */

const AXE_PATH = path.join(process.cwd(), 'node_modules', 'axe-core', 'axe.min.js')

/** What axe runs: WCAG 2.x A/AA, plus best practice so #222's two rules run. */
const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice']

/** The rules #222 found failing; each must stay at zero. */
const ISSUE_RULES = [
  'label-content-name-mismatch',
  'scrollable-region-focusable',
  'page-has-heading-one',
  'region',
]

/** A conformance-level tag (`wcag2a` … `wcag22aa`), not a criterion (`wcag253`). */
const WCAG_TAG = /^wcag2\d?a{1,2}$/

type Finding = { id: string; impact: string | null; tags: string[]; targets: string[] }

async function scan(page: Page): Promise<Finding[]> {
  await page.addScriptTag({ path: AXE_PATH })
  return page.evaluate(async (tags) => {
    type AxeNode = { target: unknown[] }
    type AxeViolation = { id: string; impact: string | null; tags: string[]; nodes: AxeNode[] }
    const axe = (
      window as unknown as {
        axe: {
          run: (
            context: Document,
            options: unknown,
          ) => Promise<{ violations: AxeViolation[] }>
        }
      }
    ).axe
    const { violations } = await axe.run(document, {
      runOnly: { type: 'tag', values: tags },
      resultTypes: ['violations'],
    })
    return violations.map((v) => ({
      id: v.id,
      impact: v.impact,
      tags: v.tags,
      targets: v.nodes.map((n) => n.target.map(String).join(' ')),
    }))
  }, TAGS)
}

/** True for a finding the gate fails on, false for one it only reports. */
function gated(f: Finding): boolean {
  return ISSUE_RULES.includes(f.id) || f.tags.some((t) => WCAG_TAG.test(t))
}

function describeFindings(findings: Finding[]): string {
  return findings
    .map((f) => `${f.id} (${f.impact ?? 'n/a'}): ${f.targets.slice(0, 5).join(' | ')}`)
    .join('\n')
}

/** Open the nav destination at `index` and wait for it to be the current one. */
async function openDestination(page: Page, index: number): Promise<string> {
  const pill = page.locator('.site-header .nav .nav-link').nth(index)
  const label = ((await pill.textContent()) ?? '').trim()
  await pill.click()
  await expect(pill).toHaveAttribute('aria-current', 'page')
  // A destination change moves focus and scrolls to the top; let that settle
  // so axe sees the view, not a frame of the transition.
  await page.waitForTimeout(300)
  return label
}

for (const viewport of [
  { width: 1366, height: 900 },
  { width: 390, height: 844 },
]) {
  test.describe(`axe at ${viewport.width}x${viewport.height}`, () => {
    test.use({ viewport })

    test('every top-level destination passes WCAG 2.2 AA and #222’s rules', async ({
      page,
    }) => {
      await page.goto('./')
      const pills = page.locator('.site-header .nav .nav-link')
      const count = await pills.count()
      // Seven today. Read from the page, so a destination added later is
      // swept without anyone remembering to list it here.
      expect(count, 'the nav rendered its destinations').toBeGreaterThan(4)

      const failures: string[] = []
      const reported: string[] = []
      const record = (view: string, findings: Finding[]) => {
        const hard = findings.filter(gated)
        const soft = findings.filter((f) => !gated(f))
        if (hard.length) failures.push(`${view}:\n${describeFindings(hard)}`)
        if (soft.length) reported.push(`${view}:\n${describeFindings(soft)}`)
      }

      for (let i = 0; i < count; i++) {
        const view = await openDestination(page, i)
        record(view, await scan(page))

        // The Library's second tab is a view of its own, and its tab was one
        // of #222's label-in-name failures. Found by id, not by name, so the
        // sweep still reaches it if its name regresses.
        if (view === 'Library') {
          await page.locator('#lib-view-concepts').click()
          await expect(page.locator('#lib-panel-concepts')).toBeVisible()
          record('Library › Concepts', await scan(page))
        }
      }

      if (reported.length) {
        // Visible in the run log; not a failure (see the header comment).
        console.log(`best-practice findings outside the gate:\n${reported.join('\n')}`)
      }
      expect(failures, failures.join('\n\n')).toEqual([])
    })

    test('one h1 that looks like the brand, one contentinfo, the footer row in a landmark', async ({
      page,
    }) => {
      await page.goto('./')
      await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1)

      // The brand became the <h1>; nothing about how it looks may change.
      // These are the values `.brand` had as a <div>: no margin (a heading's
      // 0.67em would push the nav row down), weight 700, and 1.15rem — 1rem
      // under the 719px phone query.
      const brand = await page.locator('h1.brand').evaluate((el) => {
        const s = getComputedStyle(el)
        return {
          margin: s.margin,
          fontSize: s.fontSize,
          fontWeight: s.fontWeight,
          display: s.display,
        }
      })
      expect(brand).toEqual({
        margin: '0px',
        fontSize: viewport.width <= 719 ? '16px' : '18.4px',
        fontWeight: '700',
        display: 'block',
      })

      // The layout's UPL disclaimer stays the one contentinfo
      // (BL-20260830-06); the footer row is a named region beside it.
      await expect(page.getByRole('contentinfo')).toHaveCount(1)
      const row = page.getByRole('region', { name: 'About this site' })
      await expect(row).toHaveCount(1)
      await expect(row.getByRole('button', { name: /Keyboard shortcuts/ })).toBeVisible()
      await expect(row).toContainText(/\d+ items · updated/)
    })
  })
}

// ---------------------------------------------------------------------------
// The two scroll regions, by keyboard (#222, WCAG 2.1.1)
// ---------------------------------------------------------------------------

/**
 * Press Tab from `start` until focus lands on `selector`, at most `limit`
 * times. Reports whether it got there: the claim is that the region is in the
 * Tab order, not merely focusable from script.
 */
async function tabUntil(
  page: Page,
  start: string,
  selector: string,
  limit = 80,
): Promise<boolean> {
  await page.locator(start).first().focus()
  for (let i = 0; i < limit; i++) {
    await page.keyboard.press('Tab')
    const there = await page.evaluate(
      (sel) => document.activeElement?.matches(sel) ?? false,
      selector,
    )
    if (there) return true
  }
  return false
}

test.describe('scroll regions at 1366x900 (desktop)', () => {
  test.use({ viewport: { width: 1366, height: 900 } })

  test('Tab reaches the RC passage column and the arrow keys scroll it', async ({
    page,
  }) => {
    await page.goto('./')
    await page
      .locator('.site-header .nav')
      .getByRole('button', { name: 'Reading Comprehension' })
      .click()
    const passage = page.locator('.drill-grid > .passage').first()
    await expect(passage).toBeVisible()

    // The precondition the finding needs: up here the column is its own
    // scroll region, capped at the viewport and taller inside.
    const overflow = await passage.evaluate((el) => el.scrollHeight - el.clientHeight)
    expect(overflow, 'the passage column scrolls on its own').toBeGreaterThan(0)

    expect(
      await tabUntil(page, 'main#view', '.drill-grid > .passage'),
      'Tab reaches the passage column',
    ).toBe(true)
    await expect(passage).toBeFocused()

    for (let i = 0; i < 5; i++) await page.keyboard.press('ArrowDown')
    await expect
      .poll(() => passage.evaluate((el) => el.scrollTop), {
        message: 'ArrowDown scrolls the focused passage',
      })
      .toBeGreaterThan(0)
  })
})

test.describe('scroll regions at 390x844 (phone)', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('Tab reaches a wide Library table and the arrow keys scroll it', async ({
    page,
  }) => {
    await page.goto('./')
    await page
      .locator('.site-header .nav')
      .getByRole('button', { name: 'Library' })
      .click()

    // The landing article ("LSAT exam architecture") carries a four-column
    // table, which is wider than a phone. Take whichever table overflows.
    await expect(page.locator('.lib-table-wrap').first()).toBeVisible()
    const index = await page.evaluate(() =>
      [...document.querySelectorAll<HTMLElement>('.lib-table-wrap')].findIndex(
        (el) => el.scrollWidth > el.clientWidth + 1,
      ),
    )
    expect(index, 'a library table scrolls sideways at 390px').toBeGreaterThan(-1)
    const wrap = page.locator('.lib-table-wrap').nth(index)
    await expect(wrap).toHaveAttribute('role', 'region')
    await expect(wrap).toHaveAttribute('aria-label', /^Table: /)

    // Mark the target so tabUntil can match exactly this one.
    await wrap.evaluate((el) => el.setAttribute('data-e2e-target', ''))
    expect(
      await tabUntil(page, 'main#view', '[data-e2e-target]', 120),
      'Tab reaches the wide table',
    ).toBe(true)
    await expect(wrap).toBeFocused()

    for (let i = 0; i < 5; i++) await page.keyboard.press('ArrowRight')
    await expect
      .poll(() => wrap.evaluate((el) => el.scrollLeft), {
        message: 'ArrowRight scrolls the focused table',
      })
      .toBeGreaterThan(0)
  })
})
