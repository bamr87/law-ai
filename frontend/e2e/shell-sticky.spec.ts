import { expect, test, type Page } from '@playwright/test'

/**
 * Real-layout coverage of the shell (spec 051 / BL-20260831-05).
 *
 * `__tests__/shell/ShellBehaviour.test.tsx` can only assert that the right
 * class names are on the right elements, because jsdom implements no layout:
 * `position: sticky` never sticks there, and nothing scrolls. So the shell's
 * central contract — one scroller, chrome that stays put — was asserted by
 * proxy. This spec measures it in a browser that actually lays the page out.
 *
 * The contract (frontend/ui/layout.css):
 *   1. Exactly one element scrolls page content: `.shell-scroll` on <main>.
 *      The document itself never scrolls.
 *   2. The masthead and the nav rail are outside that scroller and do not move.
 *   3. `.shell-sticky-header` parks at the top of the scroller; a
 *      `.shell-sticky-sub` toolbar parks directly beneath it.
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

type Rect = { x: number; y: number; width: number; height: number }

async function rectOf(page: Page, testId: string): Promise<Rect> {
  return page.getByTestId(testId).evaluate((el) => {
    const r = el.getBoundingClientRect()
    return { x: r.x, y: r.y, width: r.width, height: r.height }
  })
}

/**
 * Wait for the shell to stop moving.
 *
 * Routes hydrate and then fetch: a rect taken the instant `networkidle` fires
 * can still be one client render behind the final layout, which made the
 * first measurement disagree with the second by a masthead's height.
 */
async function settle(page: Page): Promise<void> {
  await expect(page.getByTestId('masthead')).toBeVisible()
  await expect(page.getByTestId('page-header')).toBeVisible()
  await settleNetwork(page)
  await page.waitForTimeout(600)
}

/** Scroll the shell's one scroller to the bottom and let sticky settle. */
async function scrollShellToBottom(page: Page): Promise<number> {
  const offset = await page.evaluate(() => {
    const main = document.querySelector('.shell-scroll') as HTMLElement | null
    if (!main) throw new Error('no .shell-scroll element on the page')
    main.scrollTop = main.scrollHeight
    return main.scrollTop
  })
  // One frame for the sticky recalculation and the condensed-header
  // transition (200ms in PageLayout).
  await page.waitForTimeout(400)
  return offset
}

/** Rect equality with a pixel of slack for font/subpixel rendering. */
function expectSameRect(after: Rect, before: Rect, what: string): void {
  expect(Math.abs(after.x - before.x), `${what}.x`).toBeLessThanOrEqual(1)
  expect(Math.abs(after.y - before.y), `${what}.y`).toBeLessThanOrEqual(1)
  expect(Math.abs(after.width - before.width), `${what}.width`).toBeLessThanOrEqual(1)
  expect(
    Math.abs(after.height - before.height),
    `${what}.height`,
  ).toBeLessThanOrEqual(1)
}

const VIEWPORTS = [
  { name: 'md', width: 820, height: 900 },
  { name: 'xl', width: 1440, height: 900 },
]

for (const viewport of VIEWPORTS) {
  test.describe(`${viewport.name} (${viewport.width}x${viewport.height})`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } })

    test('the chrome stays put while a long route scrolls', async ({ page }) => {
      await page.goto('/agents')
      await settle(page)

      const before = {
        masthead: await rectOf(page, 'masthead'),
        header: await rectOf(page, 'page-header'),
      }
      const railShown = await page.getByTestId('nav-rail').isVisible()
      const railBefore = railShown ? await rectOf(page, 'nav-rail') : null

      const scrolled = await scrollShellToBottom(page)
      expect(scrolled, 'the route is long enough to scroll').toBeGreaterThan(0)

      // 1. The document never scrolls — only `.shell-scroll` does.
      expect(await page.evaluate(() => window.scrollY)).toBe(0)
      expect(
        await page.evaluate(
          () =>
            document.scrollingElement!.scrollHeight -
            document.scrollingElement!.clientHeight,
        ),
        'the document has no scrollable overflow',
      ).toBeLessThanOrEqual(1)

      // 2. Chrome outside the scroller has not moved at all.
      expectSameRect(await rectOf(page, 'masthead'), before.masthead, 'masthead')
      if (railBefore) {
        expectSameRect(await rectOf(page, 'nav-rail'), railBefore, 'nav-rail')
      }

      // 3. The page header is still parked at the top of the scroller. Its
      //    height legitimately shrinks (it condenses on scroll), so only the
      //    position is fixed.
      const headerAfter = await rectOf(page, 'page-header')
      expect(Math.abs(headerAfter.y - before.header.y), 'header.y').toBeLessThanOrEqual(1)
      expect(headerAfter.height).toBeGreaterThan(0)
      await expect(page.getByTestId('page-header')).toBeVisible()
      await expect(page.getByTestId('page-header')).toHaveCSS(
        'position',
        'sticky',
      )
    })

    test('the page header condenses on scroll and restores at the top', async ({
      page,
    }) => {
      await page.goto('/agents')
      const header = page.getByTestId('page-header')
      await settle(page)

      await expect(header).toHaveAttribute('data-condensed', 'false')
      const tall = (await rectOf(page, 'page-header')).height

      await scrollShellToBottom(page)
      await expect(header).toHaveAttribute('data-condensed', 'true')
      const short = (await rectOf(page, 'page-header')).height
      expect(short, 'the condensed header is shorter').toBeLessThan(tall)

      await page.evaluate(() => {
        ;(document.querySelector('.shell-scroll') as HTMLElement).scrollTop = 0
      })
      await expect(header).toHaveAttribute('data-condensed', 'false')
    })

    test('a sticky toolbar parks directly beneath the page header', async ({
      page,
    }) => {
      await page.goto('/agents')
      const toolbar = page.getByTestId('sticky-toolbar').first()
      await expect(toolbar).toBeVisible()
      await settle(page)

      await scrollShellToBottom(page)

      await expect(toolbar).toBeVisible()
      await expect(toolbar).toHaveCSS('position', 'sticky')
      const header = await rectOf(page, 'page-header')
      const bar = await toolbar.evaluate((el) => {
        const r = el.getBoundingClientRect()
        return { y: r.y, height: r.height }
      })
      // Parked beneath the header, not underneath it: the toolbar's top edge
      // sits at (or just below) the header's bottom edge.
      expect(bar.y, 'toolbar sits below the header').toBeGreaterThanOrEqual(
        header.y + header.height - 1,
      )
      expect(
        bar.y - (header.y + header.height),
        'and not floating far below it',
      ).toBeLessThan(24)
    })
  })
}
