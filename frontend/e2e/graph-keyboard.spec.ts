import { expect, test, type Page } from '@playwright/test'

/**
 * Keyboard node cycling on the citation canvas (spec 051 / BL-20260906-54).
 *
 * `GraphViewer` gained arrow-key stepping and Enter-to-select in
 * BL-20260831-12, and the RTL suite can only assert the container's `tabIndex`
 * and `aria-label`: Cytoscape paints into a real `<canvas>` and does nothing at
 * all under jsdom, so `cyRef.current` is null there and the handler returns on
 * its first line. A real browser is the only place the cycling exists.
 *
 * The graph data is served by `page.route`, not by Neo4j. The behaviour under
 * test is "arrows move a cursor over the rendered nodes and Enter selects the
 * one it is on" — that needs a deterministic three-node neighborhood, not a
 * seeded corpus, and the e2e database is a shared, order-dependent thing that
 * other specs write to.
 */

const CASES = [
  { id: 'case-alpha', title: 'Alpha v. State', court: 'CO Supreme Court' },
  { id: 'case-beta', title: 'Beta v. County', court: 'CO Court of Appeals' },
  { id: 'case-gamma', title: 'Gamma v. City', court: 'CO Court of Appeals' },
]

/** Cytoscape lays the nodes out in element order, so this is the cycle order. */
const NODE_ORDER = CASES.map((c) => c.id)

function node(entry: (typeof CASES)[number]) {
  return {
    data: {
      id: entry.id,
      label: entry.title,
      type: 'Case' as const,
      title: entry.title,
      court: entry.court,
      decided_at: '2020-01-01',
      source: 'e2e-fixture',
      confidence: 0.9,
    },
  }
}

/**
 * Serve the whole `/api/graph` surface from fixtures.
 *
 * Routed on the same-origin proxy path, which is what the browser actually
 * requests since BL-20260430-07.
 */
async function stubGraphApi(page: Page): Promise<void> {
  await page.route('**/api/backend/api/graph/**', async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname
    const json = (body: unknown) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(body),
      })

    if (path.endsWith('/api/graph/stats')) {
      return json({
        available: true,
        cases: CASES.length,
        citations: 0,
        cites_edges: 2,
      })
    }
    if (path.endsWith('/api/graph/cases')) {
      return json({ available: true, cases: CASES, count: CASES.length })
    }
    if (path.endsWith('/api/graph/courts')) {
      return json({ available: true, courts: [] })
    }
    if (path.includes('/api/graph/neighborhood/')) {
      return json({
        available: true,
        nodes: CASES.map(node),
        edges: [
          {
            data: {
              id: 'e1',
              source: 'case-alpha',
              target: 'case-beta',
              type: 'CITES' as const,
            },
          },
          {
            data: {
              id: 'e2',
              source: 'case-beta',
              target: 'case-gamma',
              type: 'CITES' as const,
            },
          },
        ],
      })
    }
    // Anything else this screen asks for (paths, for instance) is not part of
    // the behaviour under test; an empty, available answer keeps it quiet.
    return json({ available: true, found: false, hops: 0, nodes: [], edges: [] })
  })
}

/** The canvas, named the way a keyboard user finds it. */
function canvas(page: Page) {
  return page.getByRole('img', { name: /citation neighborhood/i })
}

/** The inspector pane Enter fills in. */
function inspector(page: Page) {
  return page.getByTestId('node-inspector')
}

test.beforeEach(async ({ page }) => {
  await stubGraphApi(page)
  await page.goto('/graph')
  await expect(page.getByRole('main')).toBeVisible()
  // The canvas only exists once a neighborhood has loaded.
  await expect(canvas(page)).toBeVisible()
  await expect(canvas(page)).toHaveAttribute(
    'aria-label',
    /3 cases, 2 citation edges/,
  )
})

test('Enter selects the node the cursor starts on', async ({ page }) => {
  await canvas(page).focus()
  await expect(canvas(page)).toBeFocused()
  await page.keyboard.press('Enter')

  await expect(inspector(page)).toContainText(NODE_ORDER[0])
})

test('arrow keys step forward through the nodes', async ({ page }) => {
  await canvas(page).focus()
  await page.keyboard.press('ArrowRight')
  await page.keyboard.press('Enter')
  await expect(inspector(page)).toContainText(NODE_ORDER[1])

  await page.keyboard.press('ArrowRight')
  await page.keyboard.press('Enter')
  await expect(inspector(page)).toContainText(NODE_ORDER[2])
})

test('the cursor wraps rather than running off the end', async ({ page }) => {
  await canvas(page).focus()
  // One step back from the first node is the last one: a cycle, not a list
  // with an edge a keyboard can fall off.
  await page.keyboard.press('ArrowLeft')
  await page.keyboard.press('Enter')
  await expect(inspector(page)).toContainText(NODE_ORDER[NODE_ORDER.length - 1])

  await page.keyboard.press('ArrowRight')
  await page.keyboard.press('Enter')
  await expect(inspector(page)).toContainText(NODE_ORDER[0])
})

test('ArrowDown and ArrowUp move the same way, and do not scroll the page', async ({
  page,
}) => {
  await canvas(page).focus()
  const before = await page.evaluate(() => window.scrollY)
  await page.keyboard.press('ArrowDown')
  await page.keyboard.press('Enter')
  await expect(inspector(page)).toContainText(NODE_ORDER[1])

  await page.keyboard.press('ArrowUp')
  await page.keyboard.press('Enter')
  await expect(inspector(page)).toContainText(NODE_ORDER[0])
  // The handler calls preventDefault, so the arrows drive the graph instead
  // of scrolling the screen out from under it.
  expect(await page.evaluate(() => window.scrollY)).toBe(before)
})
