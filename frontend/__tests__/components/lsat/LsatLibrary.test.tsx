/**
 * Reading surface + block renderer (spec 048 T-030/T-031: FR-8, FR-9, FR-11,
 * NFR-A11Y-1, AC-6, AC-7).
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import LsatLibrary from '@/components/LsatLibrary'
import BlockRenderer, {
  SUPPORTED_BLOCK_TYPES,
} from '@/components/lsat/library/BlockRenderer'
import type { LsatBlock } from '@/lib/api'

describe('BlockRenderer', () => {
  it('renders every declared block type', () => {
    const blocks: LsatBlock[] = [
      { block_type: 'heading', level: 2, text: 'A section', anchor: 'a-section' },
      {
        block_type: 'paragraph',
        spans: [
          { kind: 'text', text: 'plain ' },
          { kind: 'strong', text: 'bold' },
          { kind: 'em', text: 'italic' },
          { kind: 'code', text: 'A → B' },
          { kind: 'link', text: 'a source', href: 'https://example.org' },
        ],
      },
      {
        block_type: 'list',
        ordered: true,
        items: [[{ kind: 'text', text: 'first' }]],
      },
      {
        block_type: 'callout',
        variant: 'example',
        title: 'A worked example',
        blocks: [{ block_type: 'paragraph', spans: [{ kind: 'text', text: 'inside' }] }],
      },
      {
        block_type: 'table',
        headers: [[{ kind: 'text', text: 'Stem' }]],
        rows: [[[{ kind: 'text', text: 'depends on assuming' }]]],
      },
      { block_type: 'notation', lines: ['A → B'], caption: 'a caption' },
    ]

    render(<BlockRenderer blocks={blocks} />)

    // Headings become real headings with the anchor id, so the outline links work.
    const headingEl = screen.getByRole('heading', { name: 'A section' })
    expect(headingEl).toHaveAttribute('id', 'a-section')
    expect(screen.getByText('bold').tagName).toBe('STRONG')
    expect(screen.getByText('italic').tagName).toBe('EM')
    expect(screen.getByText('a source')).toHaveAttribute(
      'href',
      'https://example.org',
    )
    expect(screen.getByRole('list')).toBeInTheDocument()
    expect(screen.getByLabelText(/example: A worked example/i)).toBeInTheDocument()
    expect(screen.getByText('inside')).toBeInTheDocument()
    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(screen.getByText('a caption')).toBeInTheDocument()
  })

  it('declares exactly the block types the backend can emit', () => {
    expect([...SUPPORTED_BLOCK_TYPES].sort()).toEqual([
      'callout',
      'heading',
      'list',
      'notation',
      'paragraph',
      'table',
    ])
  })

  it('renders an unknown block type as nothing rather than as source', () => {
    const rogue = [{ block_type: 'video', src: 'x' }] as unknown as LsatBlock[]
    const { container } = render(<BlockRenderer blocks={rogue} />)
    expect(container.textContent).toBe('')
  })

  it('invokes the handler for an article cross-reference', () => {
    const seen: string[] = []
    render(
      <BlockRenderer
        blocks={[
          {
            block_type: 'paragraph',
            spans: [{ kind: 'article', text: 'Other', ref_id: 'other-article' }],
          },
        ]}
        handlers={{ onArticle: (id) => seen.push(id) }}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Other' }))
    expect(seen).toEqual(['other-article'])
  })

  it('points a concept reference at the in-page glossary anchor', () => {
    render(
      <BlockRenderer
        blocks={[
          {
            block_type: 'paragraph',
            spans: [{ kind: 'concept', text: 'weaken', ref_id: 'weaken' }],
          },
        ]}
      />,
    )
    expect(screen.getByText('weaken')).toHaveAttribute('href', '#concept-weaken')
  })
})

describe('LsatLibrary', () => {
  // The reader deliberately remembers the last article in `localStorage` and
  // stamps the id into the URL fragment, so both survive between tests in one
  // jsdom document and would otherwise decide which article the next test opens.
  beforeEach(() => {
    window.localStorage.clear()
    window.history.replaceState(null, '', '/')
  })

  it('lists the contents and opens the first article', async () => {
    render(<LsatLibrary />)

    await waitFor(() =>
      expect(
        screen.getByRole('navigation', { name: /library contents/i }),
      ).toBeInTheDocument(),
    )
    const rail = screen.getByRole('navigation', { name: /library contents/i })
    expect(
      within(rail).getByRole('button', { name: /Argument Anatomy/ }),
    ).toBeInTheDocument()

    await waitFor(() =>
      expect(
        screen.getByRole('heading', { name: 'Argument Anatomy' }),
      ).toBeInTheDocument(),
    )
    expect(
      screen.getByText('Separating the conclusion from what supports it.'),
    ).toBeInTheDocument()
  })

  it('follows an inline article cross-reference into the other article', async () => {
    render(<LsatLibrary />)
    await waitFor(() => screen.getByRole('heading', { name: 'Argument Anatomy' }))

    fireEvent.click(
      screen.getByRole('button', { name: 'The Assumption Family' }),
    )
    await waitFor(() =>
      expect(
        screen.getByRole('heading', { name: 'The Assumption Family' }),
      ).toBeInTheDocument(),
    )
  })

  it('shows the in-page outline built from the article headings', async () => {
    render(<LsatLibrary />)
    await waitFor(() => screen.getByRole('heading', { name: 'Argument Anatomy' }))

    const outline = screen.getByRole('navigation', { name: /on this page/i })
    expect(within(outline).getByRole('link', { name: 'How it works' })).toHaveAttribute(
      'href',
      '#how-it-works',
    )
    expect(within(outline).getByRole('link', { name: 'Key takeaways' })).toBeInTheDocument()
  })

  it('searches and opens a hit', async () => {
    render(<LsatLibrary />)
    await waitFor(() => screen.getByRole('heading', { name: 'Argument Anatomy' }))

    fireEvent.change(screen.getByRole('searchbox', { name: /search/i }), {
      target: { value: 'negation' },
    })
    await waitFor(() =>
      expect(screen.getByText(/1 result/i)).toBeInTheDocument(),
    )
    expect(screen.getByText(/negation test settles/i)).toBeInTheDocument()
  })

  it('ignores a one-character query rather than calling the API', async () => {
    render(<LsatLibrary />)
    await waitFor(() => screen.getByRole('heading', { name: 'Argument Anatomy' }))

    fireEvent.change(screen.getByRole('searchbox', { name: /search/i }), {
      target: { value: 'n' },
    })
    await waitFor(() =>
      expect(screen.queryByText(/result/i)).not.toBeInTheDocument(),
    )
  })

  it('filters the rail by section', async () => {
    render(<LsatLibrary />)
    await waitFor(() => screen.getByRole('heading', { name: 'Argument Anatomy' }))

    const rc = screen.getByRole('button', { name: 'RC' })
    fireEvent.click(rc)
    expect(rc).toHaveAttribute('aria-pressed', 'true')
  })

  it('remembers that an article was read', async () => {
    render(<LsatLibrary />)
    await waitFor(() => screen.getByRole('heading', { name: 'Argument Anatomy' }))

    const mark = screen.getByRole('button', { name: /mark as read/i })
    fireEvent.click(mark)
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /✓ Read/ })).toBeInTheDocument(),
    )
    expect(
      JSON.parse(window.localStorage.getItem('lsat:library:read') ?? '[]'),
    ).toContain('argument-anatomy')
  })

  it('shows the prerequisite, concepts and references of an article', async () => {
    render(<LsatLibrary />)
    await waitFor(() => screen.getByRole('heading', { name: 'Argument Anatomy' }))

    expect(screen.getByText(/Concepts in this article/i)).toBeInTheDocument()
    expect(screen.getByText('Main Conclusion')).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: /LSAC — About the LSAT/ }),
    ).toBeInTheDocument()
  })
})

/**
 * The concepts merge: the catalog that used to be a tab in the practice lab
 * is a second view of this library, so the vocabulary and the material that
 * teaches it live on one screen.
 */
describe('LsatLibrary — concept catalog', () => {
  beforeEach(() => {
    window.localStorage.clear()
    window.history.replaceState(null, '', '/')
  })

  const openCatalog = async () => {
    render(<LsatLibrary />)
    await waitFor(() => screen.getByRole('heading', { name: 'Argument Anatomy' }))
    fireEvent.click(screen.getByRole('tab', { name: 'Concepts' }))
  }

  it('switches to the catalog and opens the first concept', async () => {
    await openCatalog()

    await waitFor(() =>
      expect(
        screen.getByRole('heading', { name: 'Modus tollens' }),
      ).toBeInTheDocument(),
    )
    // The rail is the same rail — one list of contents, two kinds of content.
    const rail = screen.getByRole('navigation', { name: /library contents/i })
    expect(
      within(rail).getByRole('button', { name: 'Main Conclusion' }),
    ).toBeInTheDocument()
    // The article outline is article-only; a concept has no headings.
    expect(
      screen.queryByRole('navigation', { name: /on this page/i }),
    ).not.toBeInTheDocument()
    // Modus tollens tags questions but no article — the catalog says so
    // rather than showing an empty heading.
    await waitFor(() =>
      expect(
        screen.getByText(/No article covers this concept yet/i),
      ).toBeInTheDocument(),
    )
  })

  it('lists the articles that teach a concept and the drills that use it', async () => {
    await openCatalog()
    await waitFor(() => screen.getByRole('heading', { name: 'Modus tollens' }))

    const rail = screen.getByRole('navigation', { name: /library contents/i })
    fireEvent.click(within(rail).getByRole('button', { name: 'Main Conclusion' }))

    // `taught_in` — the concept → article direction, rendered for the first
    // time by the merge.
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: /Argument Anatomy/ }),
      ).toBeInTheDocument(),
    )
    expect(screen.getByText(/Tagged on 2 bank questions/i)).toBeInTheDocument()
  })

  it('follows a taught-in article back into the reader', async () => {
    await openCatalog()
    await waitFor(() => screen.getByRole('heading', { name: 'Modus tollens' }))

    const rail = screen.getByRole('navigation', { name: /library contents/i })
    fireEvent.click(within(rail).getByRole('button', { name: 'Main Conclusion' }))
    await waitFor(() => screen.getByRole('heading', { name: /Where to learn it/ }))

    fireEvent.click(screen.getByRole('button', { name: /Argument Anatomy/ }))
    await waitFor(() =>
      expect(
        screen.getByRole('heading', { name: 'Argument Anatomy' }),
      ).toBeInTheDocument(),
    )
    expect(screen.getByRole('tab', { name: 'Articles' })).toHaveAttribute(
      'aria-selected',
      'true',
    )
  })

  it('opens a concept from the article it appears in', async () => {
    render(<LsatLibrary />)
    await waitFor(() => screen.getByRole('heading', { name: 'Argument Anatomy' }))

    // The glossary entry's name is the way out to the catalog; the
    // `#concept-<id>` anchor it sits on stays put for inline references.
    fireEvent.click(screen.getByRole('button', { name: 'Main Conclusion' }))
    await waitFor(() =>
      expect(
        screen.getByRole('heading', { name: /Where to learn it/ }),
      ).toBeInTheDocument(),
    )
    expect(screen.getByRole('tab', { name: 'Concepts' })).toHaveAttribute(
      'aria-selected',
      'true',
    )
  })

  it('filters the catalog with the shared search box', async () => {
    await openCatalog()
    await waitFor(() => screen.getByRole('heading', { name: 'Modus tollens' }))

    fireEvent.change(screen.getByRole('searchbox', { name: /search/i }), {
      target: { value: 'consequent' },
    })
    const rail = screen.getByRole('navigation', { name: /library contents/i })
    await waitFor(() =>
      expect(within(rail).getByText(/1 of 3 concepts/)).toBeInTheDocument(),
    )
    expect(
      within(rail).queryByRole('button', { name: 'Main Conclusion' }),
    ).not.toBeInTheDocument()
  })

  it('links a see-also that resolves and leaves a dangling one as text', async () => {
    await openCatalog()
    await waitFor(() => screen.getByRole('heading', { name: 'Modus tollens' }))

    const rail = screen.getByRole('navigation', { name: /library contents/i })
    fireEvent.click(
      within(rail).getByRole('button', { name: 'Necessary Assumption' }),
    )
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'See also' })).toBeInTheDocument(),
    )

    const seeAlso = screen.getByRole('heading', { name: 'See also' })
      .parentElement as HTMLElement
    // Resolved: linked, and named rather than shown as a raw id.
    expect(
      within(seeAlso).getByRole('button', { name: 'Main Conclusion' }),
    ).toBeInTheDocument()
    // Dangling: rendered as its id, with nothing to click through to.
    expect(within(seeAlso).getByText('retired-concept')).toBeInTheDocument()
    expect(
      within(seeAlso).queryByRole('button', { name: 'retired-concept' }),
    ).not.toBeInTheDocument()
  })

  it('deep-links a concept through its own URL fragment', async () => {
    // `catalog-`, not `concept-`: the latter names the glossary anchor inside
    // an article, which inline concept references still point at.
    window.history.replaceState(null, '', '#catalog-necessary-assumption')
    render(<LsatLibrary />)

    await waitFor(() =>
      expect(
        screen.getByRole('heading', { name: 'Necessary Assumption' }),
      ).toBeInTheDocument(),
    )
    expect(screen.getByRole('tab', { name: 'Concepts' })).toHaveAttribute(
      'aria-selected',
      'true',
    )
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: /The Assumption Family/ }),
      ).toBeInTheDocument(),
    )
  })
})
