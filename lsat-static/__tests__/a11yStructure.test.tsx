/**
 * Page structure and scroll regions (#222).
 *
 * An axe-core WCAG 2.2 AA scan of the export found, besides the label-in-name
 * failures `Library.test.tsx` and `pageShortcuts.test.tsx` pin:
 *
 *   - no `<h1>` anywhere — every view starts at `<h2>`;
 *   - the footer row (item count, shortcuts button, source link) outside
 *     every landmark, kept out of a `<footer>` on purpose so the layout's UPL
 *     disclaimer stays the page's one contentinfo (BL-20260830-06);
 *   - two scroll regions with nothing focusable inside, so a keyboard could
 *     not scroll them: the RC passage column and a wide library table.
 *
 * jsdom has no layout, so whether a region actually overflows is measured in
 * the browser by `e2e/a11y.spec.ts`. What can be pinned here is the markup
 * that makes each one reachable and named.
 */
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import Page from '@/app/page'
import PassagePanel from '@/components/PassagePanel'
import BlockRenderer from '@/components/library/BlockRenderer'
import type { Block } from '@/lib/types'

vi.mock('@/lib/data', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/data')>()
  const f = await import('./fixtures')
  return { ...actual, questionsFor: () => f.QUESTIONS, guideFor: () => undefined }
})

describe('the page outline', () => {
  it('has exactly one h1, and it is the brand', () => {
    render(<Page />)
    const h1s = screen.getAllByRole('heading', { level: 1 })
    expect(h1s).toHaveLength(1)
    expect(h1s[0]).toHaveClass('brand')
    expect(h1s[0]).toHaveTextContent('LSAT Practice')
    // Inside the banner, where the brand has always been.
    expect(screen.getByRole('banner')).toContainElement(h1s[0])
  })

  it('puts the footer row in a named landmark that is not a second contentinfo', () => {
    render(<Page />)
    const row = screen.getByRole('region', { name: 'About this site' })
    expect(row).toHaveClass('site-footer')
    expect(row.tagName).toBe('SECTION')
    expect(within(row).getByRole('button', { name: /Keyboard shortcuts/ }))
      .toBeInTheDocument()
    expect(row).toHaveTextContent(/\d+ items · updated/)
    expect(within(row).getByRole('link', { name: 'source' })).toBeInTheDocument()
    // The root layout's disclaimer is the contentinfo; the page adds none.
    expect(screen.queryAllByRole('contentinfo')).toHaveLength(0)
  })
})

describe('scroll regions are keyboard-reachable (WCAG 2.1.1)', () => {
  it('makes the passage column a named tab stop', () => {
    render(
      <PassagePanel
        passage={{
          id: 'rc-fixture',
          section: 'RC',
          title: 'Fixture passage',
          passage: 'A passage long enough to scroll beside its questions.',
        }}
      />,
    )
    const aside = screen.getByRole('complementary', { name: 'RC context' })
    expect(aside).toHaveAttribute('tabindex', '0')
    aside.focus()
    expect(document.activeElement).toBe(aside)
  })

  it('makes a library table a named, focusable region', () => {
    const table: Block = {
      block_type: 'table',
      headers: [
        [{ kind: 'text', text: 'Section' }],
        [{ kind: 'strong', text: 'Scored' }],
      ],
      rows: [[[{ kind: 'text', text: 'LR' }], [{ kind: 'text', text: 'Yes' }]]],
    }
    render(<BlockRenderer blocks={[table]} />)
    const region = screen.getByRole('region', { name: 'Table: Section, Scored' })
    expect(region).toHaveClass('lib-table-wrap')
    expect(region).toHaveAttribute('tabindex', '0')
    expect(within(region).getByRole('table')).toBeInTheDocument()
  })

  it('still names a table whose headers are empty', () => {
    const table: Block = {
      block_type: 'table',
      headers: [[], [{ kind: 'text', text: ' ' }]],
      rows: [],
    }
    render(<BlockRenderer blocks={[table]} />)
    expect(screen.getByRole('region', { name: 'Table' })).toHaveAttribute('tabindex', '0')
  })
})
