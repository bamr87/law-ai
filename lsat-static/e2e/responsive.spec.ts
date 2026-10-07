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

    /** Measure every target the 44px contract names, on whatever is on screen. */
    const sweep = () =>
      page.evaluate(() => {
        const bad: string[] = []
        // The 44px floor is the contract globals.css actually states, under
        // `max-width: 719px` and `pointer: coarse`: buttons, nav links, answer
        // choices, the skip link and form controls. Inline links inside prose
        // are not targets in that sense and are deliberately not padded to
        // 44px.
        const nodes = document.querySelectorAll<HTMLElement>(
          '.btn, .nav-link, .choice, .skip-link, input[type="radio"], input[type="checkbox"]',
        )
        for (const el of nodes) {
          const r = el.getBoundingClientRect()
          // Hidden controls (collapsed panels, off-screen views) are not
          // targets. The skip link is *off-screen* until focused rather than
          // hidden — it keeps its box, so it is measured like anything else.
          if (r.width === 0 || r.height === 0) continue
          if (r.height < 44) {
            bad.push(
              `${el.tagName.toLowerCase()}.${el.className} h=${r.height.toFixed(1)}`,
            )
          }
        }
        return bad
      })

    // The skip link is on this screen, and it is the one that failed: 40.8px,
    // because an inline box ignores `min-height` (globals.css `.skip-link`).
    await expect(page.locator('.skip-link')).toHaveCount(1)
    expect(await sweep(), 'overview').toEqual([])

    // `.choice` is the class the floor mostly exists for, and it exists only
    // inside a drill — an Overview-only sweep never measures one.
    await page
      .locator('.site-header .nav')
      .getByRole('button', { name: 'Logical Reasoning' })
      .click()
    await expect(page.locator('.choice').first()).toBeVisible()
    expect(
      await page.locator('.choice').count(),
      'the drill really rendered its answer choices',
    ).toBeGreaterThan(1)
    expect(await sweep(), 'logical reasoning drill').toEqual([])
  })

  test('the pin control is offered, and holds the header on screen', async ({
    page,
  }) => {
    await page.goto('./')

    // BL-20260901-05. The control first shipped `display: none` at every width
    // — a media query adds no specificity, so the blanket rule that hides it
    // above 819px won everywhere. jsdom loads no stylesheet, so only a real
    // browser can see that the toggle actually reaches the reader.
    const pin = page.locator('.header-pin')
    await expect(pin, 'the toggle renders where the header hides').toBeVisible()
    const box = await boxOf(page, '.header-pin')
    expect(box.width, 'the control has a real box').toBeGreaterThan(0)
    await expect(pin).toHaveAttribute('aria-pressed', 'false')

    await pin.click()
    await expect(pin).toHaveAttribute('aria-pressed', 'true')

    // The same journey that hides the header when it is not pinned.
    await page
      .locator('.site-header .nav')
      .getByRole('button', { name: 'Reading Comprehension' })
      .click()
    await page.waitForTimeout(600)
    await page.evaluate(() => window.scrollTo(0, 0))
    await page.waitForTimeout(400)
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
    await expect(header, 'pinned, the bar stays').not.toHaveClass(
      /site-header-hidden/,
    )
    const still = await boxOf(page, '.site-header')
    expect(still.y, 'the header is still on screen').toBeGreaterThanOrEqual(-1)
    expect(still.height, 'and still has its nav strip').toBeGreaterThan(30)
  })

  test('the nav is one scrolling strip that keeps the current pill in view', async ({
    page,
  }) => {
    await page.goto('./')

    // Seven destinations on one row: the wrapped nav is what put the header at
    // 136px (specs/047 T-013). Wrapping is a layout fact, so this counts rows.
    const rows = await page.evaluate(() => {
      const links = [
        ...document.querySelectorAll<HTMLElement>('.site-header .nav-link'),
      ]
      const tops = links.map((el) => Math.round(el.getBoundingClientRect().top))
      return { count: links.length, distinctTops: new Set(tops).size }
    })
    expect(rows.count, 'every destination is in the strip').toBeGreaterThan(4)
    expect(rows.distinctTops, 'the pills sit on one row, not wrapped').toBe(1)

    // The trailing fade is driven by a ResizeObserver rather than measured
    // once (app/page.tsx), so its answer must agree with the real geometry.
    const strip = await page.evaluate(() => {
      const nav = document.querySelector<HTMLElement>('.site-header .nav')!
      return {
        overflow: nav.scrollWidth - nav.clientWidth,
        marked: nav.className.includes('nav-scrollable'),
      }
    })
    expect(strip.marked, 'nav-scrollable matches whether the strip overflows').toBe(
      strip.overflow > 1,
    )

    // Stats is the last pill — the case that used to land the reader on a
    // destination scrolled off the end of the strip (app/page.tsx).
    await page
      .locator('.site-header .nav')
      .getByRole('button', { name: 'Stats' })
      .click()
    await page.waitForTimeout(600)
    const active = await page.evaluate(() => {
      const nav = document.querySelector<HTMLElement>('.site-header .nav')!
      const pill = nav.querySelector<HTMLElement>('[aria-current="page"]')!
      const n = nav.getBoundingClientRect()
      const a = pill.getBoundingClientRect()
      return { fromLeft: a.left - n.left, fromRight: n.right - a.right }
    })
    expect(active.fromLeft, 'the current pill is not off the left edge').toBeGreaterThan(
      -1,
    )
    expect(
      active.fromRight,
      'the current pill is not off the right edge',
    ).toBeGreaterThan(-1)
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

    // Nothing hides up here, so the pin is deliberately not offered — the
    // other half of the cascade the phone test pins (BL-20260901-05).
    await expect(page.locator('.header-pin')).toBeHidden()

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

// ---------------------------------------------------------------------------
// Writing at the reporter's viewport (#115)
// ---------------------------------------------------------------------------

/**
 * The Writing screen is the one place `.passage` appears outside a drill grid,
 * and the sticky stack's third rung used to claim it: the prompt pinned
 * partway down the viewport, painted over the editor, and — because sticky
 * establishes a stacking context — swallowed the clicks aimed at the
 * textarea, the timer and Submit. Keyboard shortcuts were the only way in.
 *
 * `__tests__/stickyScope.test.tsx` covers the cascade question on every PR.
 * This covers the part jsdom structurally cannot: whether a mouse lands on
 * the control a reader aims at. 1280×800 is the reporter's own viewport.
 */
test.describe('1280x800 (desktop, Argumentative Writing)', () => {
  test.use({ viewport: { width: 1280, height: 800 } })

  /**
   * What a click aimed at `selector` would actually hit.
   *
   * The point is the centre of the control's *visible* box, not of its layout
   * box: `elementFromPoint` answers about the viewport, and the 18-row
   * textarea is taller than 800px of screen, so its true centre is below the
   * fold even with the control perfectly usable.
   */
  async function hitAtCentreOf(page: Page, selector: string): Promise<boolean> {
    const control = page.locator(selector).first()
    await control.scrollIntoViewIfNeeded()
    return control.evaluate((el) => {
      const r = el.getBoundingClientRect()
      const top = Math.max(r.top, 0)
      const bottom = Math.min(r.bottom, window.innerHeight)
      const left = Math.max(r.left, 0)
      const right = Math.min(r.right, window.innerWidth)
      if (bottom <= top || right <= left) return false
      const hit = document.elementFromPoint((left + right) / 2, (top + bottom) / 2)
      // A click on a control's own label or inner span still reaches it, so
      // "the element or something inside it" is the honest contract.
      return hit === el || el.contains(hit)
    })
  }

  async function openFirstPrompt(page: Page): Promise<void> {
    await page.goto('./')
    await page
      .locator('.site-header .nav')
      .getByRole('button', { name: 'Argumentative Writing' })
      .click()
    await page.getByRole('button', { name: 'Open prompt' }).first().click()
    await expect(page.locator('#writing-draft')).toBeVisible()
  }

  test('the prompt does not pin, and every control takes a real click', async ({
    page,
  }) => {
    await openFirstPrompt(page)

    // The regression itself: a bare `.passage { position: sticky }` inside the
    // 820px block reached this article.
    await expect(page.locator('.passage')).toHaveCSS('position', 'static')
    expect(
      await page.locator('.passage').first().evaluate((el) => el.closest('.drill-grid')),
      'the Writing prompt is not inside a drill grid',
    ).toBeNull()

    // One vertical stack: the prompt ends before the drafting panel begins.
    const prompt = await boxOf(page, '.passage')
    const drafting = await boxOf(page, 'section[aria-label="Drafting"]')
    expect(
      drafting.y,
      'the drafting panel starts below the prompt, not on top of it',
    ).toBeGreaterThanOrEqual(prompt.y + prompt.height - 1)

    // Pinning is a scroll-time behaviour, so scrolling is the only way to see
    // it: an unpinned prompt travels the full distance with the page. Measured
    // before the hit tests below, which scroll controls into view themselves.
    const before = await boxOf(page, '.passage')
    await scrollTo(page, 300)
    const after = await boxOf(page, '.passage')
    expect(
      after.y,
      'the prompt scrolled away with the page rather than pinning',
    ).toBeLessThanOrEqual(before.y - 300 + 2)

    // And the clicks land. These are the three controls the report named.
    expect(await hitAtCentreOf(page, '#writing-draft'), 'textarea').toBe(true)
    expect(
      await hitAtCentreOf(page, '.section-timer-controls .btn'),
      'timer Start/Pause',
    ).toBe(true)
    expect(
      await hitAtCentreOf(page, '.solve-controls .btn-primary'),
      'Submit',
    ).toBe(true)
  })

  test('the review phase clears the sticky header', async ({ page }) => {
    await openFirstPrompt(page)

    // Fifty words is the submit gate (`DraftPanel.canSubmit`).
    await page
      .locator('#writing-draft')
      .fill(Array.from({ length: 60 }, (_, i) => `word${i}`).join(' '))
    await page.getByRole('button', { name: /Submit and unlock/ }).click()
    await expect(page.getByRole('region', { name: 'Review' })).toBeVisible()

    // The site header is the one element that legitimately pins up here, so
    // nothing may be drawn over it.
    expect(await hitAtCentreOf(page, '.site-header .brand'), 'site header').toBe(
      true,
    )

    // Measured from the top of the page: content scrolling *under* a sticky
    // header is correct, so the claim is about the resting layout — the review
    // panel begins below the bar rather than behind it.
    await scrollTo(page, 0)
    const header = await boxOf(page, '.site-header')
    const review = await boxOf(page, 'section[aria-label="Review"]')
    expect(
      review.y,
      'the review panel starts below the header, not sandwiched behind it',
    ).toBeGreaterThanOrEqual(header.y + header.height - 1)

    // The model response is the tallest thing on the screen and was the worst
    // of the overlap; it must be reachable by mouse too.
    const reveal = page.getByRole('button', { name: /model response/ })
    expect(await hitAtCentreOf(page, '.btn-reveal'), 'reveal control').toBe(true)
    await reveal.click()
    await expect(page.locator('.model-response').first()).toBeVisible()
  })
})

// ---------------------------------------------------------------------------
// Desktop, with the entrance animation actually running
// ---------------------------------------------------------------------------

test.describe('1280x900 (desktop, entrance animation running)', () => {
  test.use({
    viewport: { width: 1280, height: 900 },
    // Every other test here runs under reduced motion so a box measurement
    // cannot depend on where an animation happened to be. This one is about
    // the animation itself, and reduced motion switches it off entirely
    // (globals.css `.view-anim { animation: none }`), so the very defect
    // specs/047 T-013 guards against would be invisible: an animated
    // `transform` on the view wrapper creates a containing block, which breaks
    // `position: sticky` for every descendant for as long as it runs. That is
    // why the wide layout fades and the rise is reserved for narrow viewports.
    contextOptions: { reducedMotion: 'no-preference' },
  })

  test('the passage column stays sticky while the entrance animation runs', async ({
    page,
  }) => {
    await page.goto('./')
    await page
      .locator('.site-header .nav')
      .getByRole('button', { name: 'Reading Comprehension' })
      .click()
    await expect(page.locator('.passage').first()).toBeVisible()

    // Freeze the entrance mid-flight rather than racing it: a paused animation
    // still applies its effect, so a transform-based entrance would still be
    // creating the containing block while this test scrolls.
    const frozen = await page.evaluate(() => {
      const el = document.querySelector<HTMLElement>('.view-anim')!
      const anims = el.getAnimations()
      for (const a of anims) {
        a.pause()
        a.currentTime = 100
      }
      const style = getComputedStyle(el)
      return {
        playing: anims.length,
        name: style.animationName,
        transform: style.transform,
      }
    })
    // If this ever reads 0, the harness has stopped exercising the animation
    // and the rest of the case is measuring nothing.
    expect(frozen.playing, 'an entrance animation is in effect').toBeGreaterThan(0)
    expect(frozen.name, 'the view really is animated up here').not.toBe('none')
    expect(
      frozen.transform,
      'the wide entrance fades: a transform would break the sticky column',
    ).toBe('none')

    const before = await boxOf(page, '.passage')
    await scrollTo(page, 400)
    const after = await boxOf(page, '.passage')
    expect(
      after.y,
      'the passage pinned mid-animation rather than scrolling away',
    ).toBeGreaterThan(before.y - 400 + 1)
    // And it is still the animation being measured, not its aftermath.
    const stillPaused = await page.evaluate(
      () =>
        document
          .querySelector<HTMLElement>('.view-anim')!
          .getAnimations()
          .filter((a) => a.playState === 'paused').length,
    )
    expect(stillPaused, 'the animation stayed frozen across the scroll').toBeGreaterThan(
      0,
    )
  })
})
