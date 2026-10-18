/**
 * Which elements the wide-viewport sticky stack is allowed to pin (#115).
 *
 * `globals.css` pins three rungs above 820px: the site header, the drill head,
 * and the passage column. The third rung was written against the bare
 * `.passage` class, but `.passage` is not a drill-only class — `Writing`
 * reuses it for the prompt article, where it sits *above* the editor instead
 * of beside it. So the prompt pinned itself partway down the viewport, and
 * because `position: sticky` establishes a stacking context it both painted
 * over and hit-tested in front of the textarea, the timer and Submit. The
 * page was unusable with a mouse.
 *
 * jsdom computes no layout, so this cannot measure the overlap — `e2e/
 * responsive.spec.ts` does that in a real browser. What jsdom *can* do is the
 * thing that actually went wrong: match the real stylesheet's selectors
 * against the real components' DOM and ask which elements each sticky rule
 * claims. That is a cascade question, not a layout one, and it is the half
 * that is cheap enough to run on every PR.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import Drill from '@/components/Drill'
import Writing from '@/components/Writing'

vi.mock('@/lib/data', async () => {
  const f = await import('./fixtures')
  return {
    // Writing's surface.
    writingPrompts: [f.PROMPT],
    rubricFor: () => f.RUBRIC,
    // Drill's surface. `sectionMeta` is shared; the drill grid only cares that
    // a passage exists, so the WS/LR distinction is irrelevant here.
    sectionMeta: () => f.SECTION_LR,
    questionsFor: () => f.QUESTIONS,
    passageById: () => ({
      id: 'rc-fixture-01',
      section: 'RC',
      title: 'Fixture passage',
      summary: 'A short context.',
      passage: 'The passage body.',
    }),
    guideFor: () => undefined,
    playbookFor: () => undefined,
    conceptById: () => undefined,
  }
})

/** The media query the sticky stack lives behind (`globals.css`). */
const WIDE = 'min-width: 820px'

/**
 * Every selector that declares `position: sticky` inside the wide-viewport
 * block, read out of the shipped stylesheet rather than retyped here.
 *
 * `@import './base.css'` is dropped: jsdom would try to resolve it, and none
 * of the sticky stack lives there.
 */
function wideStickySelectors(): string[] {
  const css = readFileSync(
    path.resolve(__dirname, '../app/globals.css'),
    'utf8',
  ).replace(/^@import[^;]*;/m, '')

  const style = document.createElement('style')
  style.textContent = css
  document.head.appendChild(style)
  const sheet = style.sheet
  if (!sheet) throw new Error('globals.css did not parse into a stylesheet')

  const selectors: string[] = []
  for (const rule of Array.from(sheet.cssRules)) {
    if (!(rule instanceof CSSMediaRule)) continue
    if (!rule.conditionText.includes(WIDE)) continue
    for (const inner of Array.from(rule.cssRules)) {
      if (!(inner instanceof CSSStyleRule)) continue
      if (inner.style.getPropertyValue('position').trim() === 'sticky') {
        selectors.push(inner.selectorText)
      }
    }
  }
  style.remove()
  return selectors
}

let stickySelectors: string[]

beforeAll(() => {
  stickySelectors = wideStickySelectors()
  // If this ever reads empty the rest of the file is asserting nothing: the
  // stylesheet failed to parse, or the sticky stack moved out of the media
  // query. Either way the cases below would pass vacuously.
  expect(
    stickySelectors.length,
    'the wide-viewport sticky stack is still in globals.css',
  ).toBeGreaterThan(0)
})

afterEach(() => {
  window.localStorage.clear()
})

/** Every sticky selector that claims `el`. */
function claimedBy(el: Element): string[] {
  return stickySelectors.filter((selector) => el.matches(selector))
}

describe('the wide-viewport sticky stack', () => {
  it('does not pin the Writing prompt', () => {
    render(<Writing />)
    fireEvent.click(screen.getByRole('button', { name: 'Open prompt' }))

    const prompt = screen.getByRole('heading', {
      name: 'Should the town build the bypass?',
    }).parentElement!
    expect(prompt.className, 'the prompt is the `.passage` article').toContain(
      'passage',
    )

    // The structural half: the prompt is not in a drill grid, so a rule scoped
    // to one cannot reach it.
    expect(
      prompt.closest('.drill-grid'),
      'the Writing prompt is not inside a drill grid',
    ).toBeNull()

    // The cascade half, which is what actually broke: no sticky rule in the
    // wide block may match it. A bare `.passage { position: sticky }` does.
    expect(
      claimedBy(prompt),
      'no wide-viewport sticky rule claims the Writing prompt',
    ).toEqual([])
  })

  it('still pins the drill passage column', () => {
    // The other half of the same change: scoping the rule must not cost
    // LR/RC/LG the sticky column it was written for.
    render(<Drill section="RC" />)

    const passage = document.querySelector('.passage')!
    expect(passage, 'the drill rendered its passage column').not.toBeNull()
    expect(
      passage.parentElement?.className,
      'the passage is a direct child of the drill grid',
    ).toContain('drill-grid')
    expect(
      claimedBy(passage),
      'the drill passage is still pinned above 820px',
    ).not.toEqual([])
  })

  it('still pins the drill head', () => {
    render(<Drill section="RC" />)
    const head = document.querySelector('.drill-head')!
    expect(claimedBy(head), 'the drill head is still pinned').not.toEqual([])
  })
})
