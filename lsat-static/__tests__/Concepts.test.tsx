/**
 * The concept catalog's cross-links (BL-20260905-03).
 *
 * The catalog moved inside the library so a concept could name the material
 * that teaches it — `articlesTeaching` is the whole reason the merge happened,
 * and it was covered only by structural checks on the exported artifact. This
 * suite is about the card: what it lists, and where each link goes.
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import Concepts from '@/components/Concepts'

vi.mock('@/lib/data', async () => {
  const f = await import('./fixtures')
  const base = f.libraryData()
  return {
    ...base,
    // A third concept nothing teaches yet: the catalog has to say so in words
    // rather than render an empty list.
    content: {
      ...base.content,
      concepts: [
        ...f.LIBRARY_CONCEPTS,
        {
          id: 'red-herring',
          name: 'Red herring',
          summary: 'An irrelevant distractor.',
          sections: ['LR'],
        },
      ],
    },
  }
})

function card(name: string): HTMLElement {
  return screen.getByRole('heading', { name }).closest('li') as HTMLElement
}

describe('concept cards', () => {
  it('lists every article that teaches the concept, by tag or by inline span', () => {
    render(<Concepts />)
    const assumption = card('Necessary assumption')
    const taught = within(assumption).getByText('Articles on this concept')
      .parentElement as HTMLElement
    expect(
      within(taught)
        .getAllByRole('button')
        .map((b) => b.textContent),
    ).toEqual(['What the LSAT measures', 'The assumption family'])
    // The count in the header agrees with the list under it.
    expect(assumption).toHaveTextContent('taught in 2 articles')
  })

  it('opens the article the reader picked', () => {
    const onOpenArticle = vi.fn()
    render(<Concepts onOpenArticle={onOpenArticle} />)
    fireEvent.click(
      within(card('Conditional chain')).getByRole('button', {
        name: 'Conditional diagramming',
      }),
    )
    expect(onOpenArticle).toHaveBeenCalledWith('lib-diagramming')
  })

  it('says so when no article covers a concept yet', () => {
    render(<Concepts />)
    const orphan = card('Red herring')
    expect(orphan).toHaveTextContent('No article covers this concept yet.')
    expect(orphan).toHaveTextContent('taught in 0 articles')
    expect(
      within(orphan).queryByRole('button', { name: /What the LSAT/ }),
    ).toBeNull()
  })

  it('anchors see-also at the sibling card, and shows a dangling id as text', () => {
    render(<Concepts />)
    // Each card is its own anchor target, so a `#catalog-<id>` link works with
    // no script at all.
    expect(card('Conditional chain')).toHaveAttribute('id', 'catalog-conditional-chain')
    const related = within(card('Necessary assumption')).getByText('Related')
      .parentElement as HTMLElement
    expect(within(related).getByRole('link', { name: 'Conditional chain' })).toHaveAttribute(
      'href',
      '#catalog-conditional-chain',
    )
    // An id the catalog cannot resolve is not rendered as a broken link.
    const dangling = within(card('Conditional chain')).getByText('Related')
      .parentElement as HTMLElement
    expect(within(dangling).queryByRole('link')).toBeNull()
    expect(dangling).toHaveTextContent('no-such-concept')
  })

  it('names the reading tracks that cover the concept, and opens them', () => {
    const onOpenTrack = vi.fn()
    render(<Concepts onOpenTrack={onOpenTrack} />)
    fireEvent.click(
      within(card('Necessary assumption')).getByRole('button', { name: /Start here/ }),
    )
    expect(onOpenTrack).toHaveBeenCalledWith('track-start')
  })
})

describe('catalog filters', () => {
  it('narrows by section', () => {
    render(<Concepts />)
    fireEvent.click(screen.getByRole('button', { name: 'Logic Games' }))
    expect(screen.getByText('1 of 3 concepts')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Conditional chain' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Necessary assumption' })).toBeNull()
  })

  it('searches name, summary, detail and examples', () => {
    render(<Concepts />)
    const box = screen.getByRole('searchbox')
    fireEvent.change(box, { target: { value: 'destroys the conclusion' } })
    expect(screen.getByText('1 of 3 concepts')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Necessary assumption' })).toBeInTheDocument()

    fireEvent.change(box, { target: { value: 'nothing here' } })
    expect(screen.getByText('No concept matches that filter.')).toBeInTheDocument()
  })
})

describe('per-concept links (BL-20260905-04)', () => {
  it('gives every card a URL of its own', () => {
    // The layout stays a single scrollable catalog — the divergence from the
    // platform's rail + reader is deliberate and recorded in the README —
    // but the capability is not allowed to diverge: one concept, one link.
    render(<Concepts />)
    for (const [id, name] of [
      ['necessary-assumption', 'Necessary assumption'],
      ['conditional-chain', 'Conditional chain'],
      ['red-herring', 'Red herring'],
    ]) {
      expect(card(name)).toHaveAttribute('id', `catalog-${id}`)
      expect(
        within(card(name)).getByRole('link', { name: `Link to ${name}` }),
      ).toHaveAttribute('href', `#catalog-${id}`)
    }
  })

  it('lands focus on the card a deep link named', () => {
    render(<Concepts focusId="red-herring" />)
    expect(document.activeElement).toBe(card('Red herring'))
  })

  it('does nothing when the link names no concept in this bundle', () => {
    render(<Concepts focusId="not-a-concept" />)
    expect(document.activeElement).toBe(document.body)
  })

  it('leaves focus alone when the catalog was opened by the switcher', () => {
    render(<Concepts focusId={null} />)
    expect(document.activeElement).toBe(document.body)
  })
})
