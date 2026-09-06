import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { expect, test, type Page } from '@playwright/test'

/**
 * Accessibility smoke over the module catalog (spec 051 / BL-20260831-09).
 *
 * `scripts/ux_audit.py` is a stdlib grep gate: it can see that a `<nav>` has a
 * name in the source, but it cannot compute a contrast ratio, resolve an
 * accessible name through ARIA, or watch focus move. That half of the UX
 * review was done by hand, once per review pass. This spec runs it on every
 * nightly instead.
 *
 * axe-core is injected from node_modules rather than pulled in through
 * `@axe-core/playwright`: the library is already in the frontend's lockfile,
 * and the wrapper adds a dependency for `page.evaluate(axe.run)`.
 */

// Resolved from the runner's cwd (`/app` in the e2e image), not from
// `import.meta.url`: Playwright transpiles these specs to CommonJS because
// frontend/package.json declares no `"type": "module"`.
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

const AXE_PATH = path.join(
  process.cwd(),
  'node_modules',
  'axe-core',
  'axe.min.js',
)

/** WCAG 2.1 AA — covers contrast, name-role-value, and structure. */
const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']

/** The six routes in frontend/lib/modules/catalog.ts. */
const ROUTES = ['/', '/agents', '/analysis', '/graph', '/lsat', '/settings']

type Violation = {
  id: string
  impact: string | null
  help: string
  nodes: { target: string[] }[]
}

declare global {
  interface Window {
    axe: {
      run: (
        context: unknown,
        options: unknown,
      ) => Promise<{ violations: Violation[] }>
    }
  }
}

async function analyse(page: Page): Promise<Violation[]> {
  await page.addScriptTag({ path: AXE_PATH })
  return page.evaluate(async (tags) => {
    const { violations } = await window.axe.run(document, {
      runOnly: { type: 'tag', values: tags },
      // Screenshots and traces are the review artefact; axe's own iframe
      // instrumentation is not needed for a single-document app shell.
      resultTypes: ['violations'],
    })
    return violations.map((v) => ({
      id: v.id,
      impact: v.impact ?? null,
      help: v.help,
      nodes: v.nodes.map((n) => ({ target: n.target })),
    }))
  }, TAGS)
}

function describeViolations(violations: Violation[]): string {
  return violations
    .map(
      (v) =>
        `${v.id} (${v.impact ?? 'n/a'}): ${v.help}\n    ` +
        v.nodes
          .slice(0, 5)
          .map((n) => n.target.join(' '))
          .join('\n    '),
    )
    .join('\n')
}

/**
 * Pre-existing debt, recorded once and ratcheted down (never up).
 *
 * The six routes carry real violations today — a palette that puts
 * `text-slate-500` on `bg-slate-950`, and one scroll container without a
 * keyboard entry point. Failing every route on day one would mean the gate is
 * switched off within a week, so instead the baseline records how many nodes
 * each known rule touches per route:
 *
 *   - a rule id NOT in the baseline fails immediately;
 *   - a rule in the baseline that no longer fires is a win, and the file
 *     should be re-recorded without it.
 *
 * The recorded node counts are triage information, not an assertion: several
 * offending elements are rows of live data (the backlog list, the agent-runs
 * list), so the count moves with the database and a count gate would flake
 * nightly. The rule-id set does not move with data.
 *
 * Re-record with `make test-e2e E2E_ARGS='e2e/a11y.spec.ts'` after setting
 * E2E_A11Y_UPDATE_BASELINE=1, and shrink the numbers — never grow them to make
 * a failure go away.
 */
const BASELINE_PATH = path.join(process.cwd(), 'e2e', 'a11y-baseline.json')
const UPDATING = process.env.E2E_A11Y_UPDATE_BASELINE === '1'

type Baseline = Record<string, Record<string, number>>

const baseline: Baseline = existsSync(BASELINE_PATH)
  ? (JSON.parse(readFileSync(BASELINE_PATH, 'utf-8')) as Baseline)
  : {}
const recorded: Baseline = {}

/** Nodes per rule id, for one route. */
function tally(violations: Violation[]): Record<string, number> {
  const counts: Record<string, number> = {}
  for (const v of violations) counts[v.id] = (counts[v.id] ?? 0) + v.nodes.length
  return counts
}

test.afterAll(() => {
  if (!UPDATING) return
  const merged = { ...baseline, ...recorded }
  writeFileSync(BASELINE_PATH, `${JSON.stringify(merged, null, 2)}\n`)
  console.log(`a11y baseline written to ${BASELINE_PATH}`)
})

for (const route of ROUTES) {
  test(`${route} has no new WCAG 2.1 AA violations`, async ({ page }) => {
    await page.goto(route)
    await expect(page.getByRole('main')).toBeVisible()
    await settleNetwork(page)

    const violations = await analyse(page)
    const counts = tally(violations)
    recorded[route] = counts
    if (UPDATING) return

    const allowed = baseline[route] ?? {}
    const introduced = violations.filter((v) => !(v.id in allowed))
    expect(
      introduced.map((v) => v.id),
      `new accessibility violations on ${route}:\n${describeViolations(introduced)}\n`,
    ).toEqual([])

    for (const [rule, count] of Object.entries(counts)) {
      const was = allowed[rule]
      if (count !== was) {
        console.log(`a11y ${route}: ${rule} ${was} -> ${count} nodes`)
      }
    }
  })

  test(`${route} starts its tab order on the skip link`, async ({ page }) => {
    await page.goto(route)
    await expect(page.getByRole('main')).toBeVisible()

    await page.keyboard.press('Tab')
    const first = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null
      if (!el || el === document.body) return null
      return {
        text: (el.textContent ?? '').trim(),
        href: el.getAttribute('href'),
        // A focused element that is display:none / visibility:hidden or has
        // zero area is a focus trap waiting to happen.
        visible: el.getClientRects().length > 0,
      }
    })
    expect(first, 'the first Tab lands somewhere').not.toBeNull()
    expect(first!.visible, 'the first focus target is rendered').toBe(true)
    expect(first!.href, 'the first stop is the skip link').toBe('#main')
  })

  test(`${route} never focuses a hidden element while tabbing the chrome`, async ({
    page,
  }) => {
    await page.goto(route)
    await expect(page.getByRole('main')).toBeVisible()

    const offenders: string[] = []
    for (let i = 0; i < 15; i += 1) {
      await page.keyboard.press('Tab')
      const bad = await page.evaluate(() => {
        const el = document.activeElement as HTMLElement | null
        if (!el || el === document.body) return null
        const style = getComputedStyle(el)
        const hidden =
          style.visibility === 'hidden' ||
          style.display === 'none' ||
          el.getClientRects().length === 0 ||
          el.closest('[aria-hidden="true"]') !== null
        // `.sr-only` is clipped to a pixel on purpose and is a legitimate
        // focus target (the skip link is one), so it is judged by aria-hidden
        // and computed style rather than by size alone.
        return hidden ? `${el.tagName.toLowerCase()}.${el.className}` : null
      })
      if (bad) offenders.push(`step ${i + 1}: ${bad}`)
    }
    expect(offenders).toEqual([])
  })
}
