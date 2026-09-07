/**
 * The landing view says what the published site cannot do (BL-20260831-25).
 *
 * The gap between this site and the full lab was stated only in the repo
 * README — which nobody reading the published site sees — and as a code
 * comment in `SolveAssist`. Discovering a missing feature by looking for it
 * and failing is the worst way to learn it is missing.
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import Overview from '@/components/Overview'

vi.mock('@/lib/data', async () => {
  const f = await import('./fixtures')
  return {
    content: {
      counts: { total: 3, LR: 3, RC: 0, LG: 0, WS: 0, writing_prompts: 1 },
      sections: [f.SECTION_LR, f.SECTION_WS],
    },
  }
})

describe('Overview', () => {
  it('names the three features the static site does not have', () => {
    render(<Overview onStart={vi.fn()} />)
    const note = screen
      .getByText('What this site does not have')
      .closest('details') as HTMLElement
    expect(note).toBeInTheDocument()
    for (const missing of [
      'AI tutor',
      'blind answer cross-check',
      'server-side stats',
    ]) {
      expect(note).toHaveTextContent(missing)
    }
    // ...and says where the whole thing lives.
    expect(within(note).getByRole('link', { name: 'open source' })).toHaveAttribute(
      'href',
      'https://github.com/bamr87/law-ai',
    )
  })

  it('keeps the note out of the way until it is asked for', () => {
    // One collapsed line: findable before someone goes looking for a missing
    // feature, without competing with the section cards.
    render(<Overview onStart={vi.fn()} />)
    const note = screen
      .getByText('What this site does not have')
      .closest('details') as HTMLDetailsElement
    expect(note.open).toBe(false)
  })

  it('still opens each section', () => {
    const onStart = vi.fn()
    render(<Overview onStart={onStart} />)
    fireEvent.click(screen.getAllByRole('button')[0])
    expect(onStart).toHaveBeenCalled()
  })
})
