import { expect, test, type Page } from '@playwright/test'

/**
 * Responsive measurements for the static site (spec 051 / BL-20260901-03).
 *
 * specs/047 T-013/T-014 list exact numbers — phone header ≤ 85px at rest,
 * ~60px condensed, translated off-screen past 220px of scroll, restored on
 * focus; 44px touch targets; no horizontal overflow; a one-row nav and a
 * sticky passage column at 1280px — and every one of them was verified by
 * driving a browser by hand.
 *
 * Neither of the automated gates that exist can replace that:
 * `scripts/ux_audit.py` is a stdlib source grep, and the Vitest suite runs in
 * jsdom, which has no layout engine at all. Header height and `position:
 * sticky` are layout facts, so this measures them in a real browser against
 * the built export.
 *
 * Tolerances are ±2px: font rasterisation differs between the CI image and a
 * developer's machine, and these are box measurements, not pixel diffs.
 */

/** Header state machine thresholds, from app/page.tsx. */
const HIDE_AFTER_PX = 220

async function boxOf(page: Page, selector: string) {
  return page.locator(selector).first().evaluate((el) => {
    const r = el.getBoundingClientRect()
    return { x: r.x, y: r.y, width: r.width, height: r.height }
  })
}

async function scrollTo(page: Page, y: number): Promise<void> {
  await page.evaluate((to) => window.scrollTo(0, to), y)
  // The header listener runs in requestAnimationFrame; the class transition is
  // ~260ms and disabled by reducedMotion, but the class flip still needs a
  // frame or two.
  await page.waitForTimeout(250)
}

// ---------------------------------------------------------------------------
// Phone
// ---------------------------------------------------------------------------

test.describe('390x844 (phone)', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('the header is compact at rest and condenses on scroll', async ({
    page,
  }) => {
    await page.goto('./')
    await expect(page.locator('.site-header')).toBeVisible()

    const atTop = await boxOf(page, '.site-header')
    // Was 136px of chrome (brand + subtitle + a nav wrapped to three lines).
    expect(atTop.height, 'header at rest').toBeLessThanOrEqual(85)
    expect(atTop.y, 'header starts at the top of the viewport').toBeLessThanOrEqual(1)

    await scrollTo(page, 60)
    await expect(page.locator('.site-header')).toHaveClass(
      /site-header-condensed/,
    )
    const condensed = await boxOf(page, '.site-header')
    expect(condensed.height, 'condensed header').toBeLessThanOrEqual(64)
    expect(condensed.height, 'the nav strip survives').toBeGreaterThan(30)
  })

  test('the header slides away past the hide threshold and comes back on focus', async ({
    page,
  }) => {
    await page.goto('./')
    // The overview alone may not be tall enough to reach the hide threshold;
    // a reading-comprehension drill is. Nav buttons carry the full section
    // name as their aria-label (app/page.tsx `NAV`).
    await page.getByRole('button', { name: 'Reading Comprehension' }).click()
    // Changing view moves focus, which scrolls; let that settle and start the
    // measurement from a known position, or the direction handler's
    // "ignore jitter" branch keeps whatever state that scroll left behind.
    await page.waitForTimeout(600)
    await page.evaluate(() => window.scrollTo(0, 0))
    await page.waitForTimeout(400)

    // Two steps, as a reader actually scrolls. One jump straight past the
    // threshold does not work and should not: condensing collapses the brand
    // row, the document gets shorter, and the browser clamps scrollY back up —
    // which the direction handler correctly reads as a scroll upward and
    // answers by restoring the header. Step one condenses and settles the new
    // height; step two is the unambiguous downward move being tested.
    await page.evaluate(() => window.scrollTo(0, 120))
    await page.waitForTimeout(350)

    const reached = await page.evaluate((threshold) => {
      const max = document.scrollingElement!.scrollHeight - window.innerHeight
      window.scrollTo(0, Math.min(threshold + 80, max - 60))
      return window.scrollY
    }, HIDE_AFTER_PX)
    await page.waitForTimeout(400)
    expect(reached, 'the page is long enough to hide the header').toBeGreaterThan(
      HIDE_AFTER_PX,
    )

    const header = page.locator('.site-header')
    await expect(header).toHaveClass(/site-header-hidden/)

    // `transform: translateY(-101%)` — the bar is off the top edge, not
    // merely shorter, so the whole box sits above y=0.
    const hidden = await boxOf(page, '.site-header')
    expect(hidden.y + hidden.height, 'header is off-screen').toBeLessThanOrEqual(1)

    // A keyboard user tabbing into the nav must get it back (page.tsx onFocus).
    await page.locator('.site-header .nav-link').first().focus()
    await page.waitForTimeout(250)
    await expect(header).not.toHaveClass(/site-header-hidden/)
    const restored = await boxOf(page, '.site-header')
    expect(restored.y, 'header is back on screen').toBeGreaterThanOrEqual(-1)
  })

  test('every interactive control clears 44px', async ({ page }) => {
    await page.goto('./')
    const tooSmall = await page.evaluate(() => {
      const bad: string[] = []
      // The 44px floor is the contract globals.css actually states, under
      // `max-width: 719px` and `pointer: coarse`: buttons, nav links, answer
      // choices and form controls. Inline links inside prose are not targets
      // in that sense and are deliberately not padded to 44px.
      const nodes = document.querySelectorAll<HTMLElement>(
        '.btn, .nav-link, .choice, input[type="radio"], input[type="checkbox"]',
      )
      for (const el of nodes) {
        const r = el.getBoundingClientRect()
        // Hidden controls (collapsed panels, off-screen views) are not targets.
        if (r.width === 0 || r.height === 0) continue
        if (r.height < 44) {
          bad.push(`${el.tagName.toLowerCase()}.${el.className} h=${r.height.toFixed(1)}`)
        }
      }
      return bad
    })
    expect(tooSmall).toEqual([])
  })

  test('nothing overflows horizontally', async ({ page }) => {
    await page.goto('./')
    for (const view of ['Overview', 'Drill', 'Stats']) {
      const button = page.getByRole('button', { name: new RegExp(view, 'i') })
      if (await button.first().isVisible()) await button.first().click()
      await page.waitForTimeout(150)
      const overflow = await page.evaluate(() => {
        const el = document.scrollingElement!
        return el.scrollWidth - el.clientWidth
      })
      expect(overflow, `${view} has no horizontal scroll`).toBeLessThanOrEqual(1)
    }
  })
})

// ---------------------------------------------------------------------------
// Desktop
// ---------------------------------------------------------------------------

test.describe('1280x900 (desktop)', () => {
  test.use({ viewport: { width: 1280, height: 900 } })

  test('the header is one row and never moves', async ({ page }) => {
    await page.goto('./')
    const atTop = await boxOf(page, '.site-header')
    // --site-header-h is 3.75rem = 60px, deliberately a hair under the real
    // height so the sticky rung below tucks rather than leaving a gap.
    // Resolved through a probe element, because a custom property's computed
    // value is the specified token (`3.75rem`), not a pixel length.
    const token = await page.evaluate(() => {
      const probe = document.createElement('div')
      probe.style.height = 'var(--site-header-h)'
      probe.style.position = 'absolute'
      document.body.appendChild(probe)
      const px = probe.getBoundingClientRect().height
      probe.remove()
      return px
    })
    expect(token, '--site-header-h resolves to ~60px').toBeGreaterThan(55)
    expect(token, '--site-header-h resolves to ~60px').toBeLessThan(65)
    // specs/047 T-014 measured 61px here, and the token is deliberately a hair
    // under the real height so the rung below tucks rather than leaving a gap.
    expect(atTop.height, 'real header height ≈ 61px').toBeGreaterThanOrEqual(58)
    expect(atTop.height, 'real header height ≈ 61px').toBeLessThanOrEqual(65)
    expect(atTop.height, 'the token sits just under it').toBeGreaterThanOrEqual(
      token,
    )

    // The nav sits on the brand's row, not wrapped beneath it.
    const brand = await boxOf(page, '.brand')
    const nav = await boxOf(page, '.site-header .nav')
    expect(Math.abs(nav.y - brand.y), 'nav shares the brand row').toBeLessThan(24)

    // The scroll-directional header is phone-only (max-width: 819px).
    await scrollTo(page, HIDE_AFTER_PX + 300)
    await expect(page.locator('.site-header')).toHaveCSS('transform', 'none')
    const scrolled = await boxOf(page, '.site-header')
    expect(Math.abs(scrolled.height - atTop.height), 'height held').toBeLessThanOrEqual(2)
  })

  test('the reading-comprehension passage column stays sticky', async ({
    page,
  }) => {
    await page.goto('./')
    await page.getByRole('button', { name: 'Reading Comprehension' }).click()

    // `.passage` is the RC context aside (components/PassagePanel.tsx) — every
    // RC question in the bank is passage-backed, so this must be present.
    const passage = page.locator('.passage')
    await expect(passage.first()).toBeVisible()
    await expect(passage.first()).toHaveCSS('position', 'sticky')
    // The drill head above it pins too — the same three-rung stack.
    await expect(page.locator('.drill-head').first()).toHaveCSS(
      'position',
      'sticky',
    )

    const before = await boxOf(page, '.passage')
    await scrollTo(page, 400)
    const after = await boxOf(page, '.passage')
    expect(
      after.y,
      'the passage pinned rather than scrolling away with the page',
    ).toBeGreaterThan(before.y - 400 + 1)
  })
})
