/**
 * Reading surface + block renderer (spec 048 T-030/T-031: FR-8, FR-9, FR-11,
 * NFR-A11Y-1, AC-6, AC-7).
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import LsatLibrary from '@/components/LsatLibrary'
import BlockRenderer, {
  SUPPORTED_BLOCK_TYPES,
} from '@/components/lsat/library/BlockRenderer'
import type { LsatBlock } from '@/lib/api'
import { INSTANCE_SCOPE } from '@/lib/scope/instance'
import { upsertSettingValue } from '@/lib/scope/store'
import { libraryContents, libraryOutline } from '@/lib/settings/catalog'
import { resetLayout } from '@/lib/shell/layout'

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

    expect(
      screen.getByRole('heading', { name: 'Concepts in this article' }),
    ).toBeInTheDocument()
    expect(screen.getByText('Main Conclusion')).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: /LSAC — About the LSAT/ }),
    ).toBeInTheDocument()
  })

  it('renders every field the article carries, in the template order', async () => {
    render(<LsatLibrary />)
    await waitFor(() => screen.getByRole('heading', { name: 'Argument Anatomy' }))

    // Header: kind · level · reading time · word count · sections, then tags.
    // Scoped to the entry: the rail groups articles under the same kind label.
    const entry = screen.getByRole('article')
    expect(within(entry).getByText('Foundations')).toBeInTheDocument()
    expect(within(entry).getByText('Foundation')).toBeInTheDocument()
    expect(within(entry).getByText('700 words')).toBeInTheDocument()
    expect(
      within(within(entry).getByRole('list', { name: 'Tags' })).getByText('conclusion'),
    ).toBeInTheDocument()

    // Cross-reference sections in order, each anchored for the outline.
    const headings = screen
      .getAllByRole('heading', { level: 2 })
      .map((h) => h.textContent)
    const order = ['Concepts in this article', 'Related', 'Reading tracks', 'References']
    expect(order.map((t) => headings.indexOf(t))).toEqual(
      [...order.map((t) => headings.indexOf(t))].sort((a, b) => a - b),
    )
    expect(document.getElementById('entry-concepts')).not.toBeNull()
    expect(document.getElementById('entry-references')).not.toBeNull()

    // Provenance carries the status too.
    expect(screen.getByText(/revision 1 · last reviewed 2026-09-03 · reviewed/)).toBeInTheDocument()
  })

  it('lists the template sections in the outline, after the body headings', async () => {
    render(<LsatLibrary />)
    await waitFor(() => screen.getByRole('heading', { name: 'Argument Anatomy' }))

    const outline = screen.getByRole('navigation', { name: /on this page/i })
    const links = within(outline)
      .getAllByRole('link')
      .map((a) => a.getAttribute('href'))
    expect(links.slice(0, 2)).toEqual(['#how-it-works', '#key-takeaways'])
    expect(links).toContain('#entry-concepts')
    expect(links).toContain('#entry-tracks')
  })

  it('opens a reading track from the article that belongs to it', async () => {
    render(<LsatLibrary />)
    await waitFor(() => screen.getByRole('heading', { name: 'Argument Anatomy' }))

    fireEvent.click(screen.getByRole('button', { name: /^Start Here/ }))
    expect(screen.getByRole('combobox')).toHaveValue('start-here')
    expect(screen.getByText('Finish with an accurate model of the test.')).toBeInTheDocument()
  })
})

/**
 * The concepts merge: the catalog that used to be a tab in the practice lab
 * is a second view of this library, so the vocabulary and the material that
 * teaches it live on one screen.
 */
describe('LsatLibrary — layout preferences (spec 050)', () => {
  beforeEach(() => {
    window.localStorage.clear()
    window.history.replaceState(null, '', '/')
  })
  // The settings store caches its snapshot, so clearing storage is not enough.
  afterEach(() => resetLayout())

  it('drops the side columns by preference and keeps the contents reachable', async () => {
    for (const def of [libraryOutline, libraryContents]) {
      upsertSettingValue({
        scopeId: INSTANCE_SCOPE.id,
        key: def.key,
        value: false,
        locked: false,
      })
    }
    render(<LsatLibrary />)
    await waitFor(() => screen.getByRole('heading', { name: 'Argument Anatomy' }))

    expect(
      screen.queryByRole('navigation', { name: 'On this page' }),
    ).not.toBeInTheDocument()

    // The rail waits to be asked for, and the disclosure that asks serves
    // every width now — not only the narrow one.
    const rail = screen.getByRole('navigation', { name: /library contents/i })
    expect(rail.className).toContain('hidden')
    const disclosure = screen.getByRole('button', { name: /Browse contents/ })
    expect(disclosure.className).not.toContain('@min-[48rem]:hidden')
    fireEvent.click(disclosure)
    expect(rail.className).toContain('block')
    expect(
      within(rail).getByRole('button', { name: /Argument Anatomy/ }),
    ).toBeInTheDocument()
  })
})

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
      within(rail).getByRole('button', { name: /^Main Conclusion/ }),
    ).toBeInTheDocument()
    // Same row shape as the article rail: the second line says what you get.
    // (`\s*`: jsdom applies no stylesheet, so the two lines concatenate
    // without the space a browser's block layout would put between them.)
    expect(
      within(rail).getByRole('button', {
        name: /^Main Conclusion\s*taught in 1 article/,
      }),
    ).toBeInTheDocument()
    // The outline column lists the template's sections on this view too.
    const outline = screen.getByRole('navigation', { name: /on this page/i })
    expect(
      within(outline).getByRole('link', { name: 'Articles on this concept' }),
    ).toHaveAttribute('href', '#entry-articles')
    // Modus tollens tags questions but no article — the catalog says so
    // rather than showing an empty heading.
    await waitFor(() =>
      expect(
        screen.getByText(/No article covers this concept yet/i),
      ).toBeInTheDocument(),
    )
  })

  it('marks a concept as read, in the same store as the articles', async () => {
    await openCatalog()
    await waitFor(() => screen.getByRole('heading', { name: 'Modus tollens' }))

    fireEvent.click(screen.getByRole('button', { name: /mark as read/i }))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /✓ Read/ })).toBeInTheDocument(),
    )
    const stored = JSON.parse(
      window.localStorage.getItem('lsat:library:read') ?? '[]',
    )
    // Prefixed, so a concept and an article sharing an id never collide and
    // the existing bare article ids stay valid.
    expect(stored).toContain('concept:modus-tollens')
    const rail = screen.getByRole('navigation', { name: /library contents/i })
    expect(within(rail).getByText(/1 of 3 read/)).toBeInTheDocument()
  })

  it('lists the articles that teach a concept and the drills that use it', async () => {
    await openCatalog()
    await waitFor(() => screen.getByRole('heading', { name: 'Modus tollens' }))

    const rail = screen.getByRole('navigation', { name: /library contents/i })
    fireEvent.click(within(rail).getByRole('button', { name: /^Main Conclusion/ }))

    // `taught_in` — the concept → article direction, rendered for the first
    // time by the merge — under the same heading shape as the article side.
    await waitFor(() =>
      expect(
        screen.getByRole('heading', { name: 'Articles on this concept' }),
      ).toBeInTheDocument(),
    )
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: /^Argument Anatomy/ }),
      ).toBeInTheDocument(),
    )
    // The drill count is an action, exactly where an article puts it.
    expect(
      screen.getByRole('link', { name: 'Drill this (2 questions)' }),
    ).toHaveAttribute('href', '/lsat')
    // The concept reaches a track through the article that teaches it.
    expect(screen.getByRole('button', { name: /^Start Here/ })).toBeInTheDocument()
  })

  it('follows a taught-in article back into the reader', async () => {
    await openCatalog()
    await waitFor(() => screen.getByRole('heading', { name: 'Modus tollens' }))

    const rail = screen.getByRole('navigation', { name: /library contents/i })
    fireEvent.click(within(rail).getByRole('button', { name: /^Main Conclusion/ }))
    await waitFor(() => screen.getByRole('button', { name: /^Argument Anatomy/ }))

    fireEvent.click(screen.getByRole('button', { name: /^Argument Anatomy/ }))
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

    // The concept card is the way out to the catalog; the `#concept-<id>`
    // anchor it sits on stays put for inline references.
    expect(document.getElementById('concept-main-conclusion')).not.toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /^Main Conclusion/ }))
    await waitFor(() =>
      expect(
        screen.getByRole('heading', { name: 'Articles on this concept' }),
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
      within(rail).getByRole('button', { name: /^Necessary Assumption/ }),
    )
    // "Related" on a concept is `see_also`, under the same heading and card
    // shape as an article's related articles.
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Related' })).toBeInTheDocument(),
    )

    const related = document.getElementById('entry-related') as HTMLElement
    // Resolved: a card, named rather than shown as a raw id.
    expect(
      within(related).getByRole('button', { name: /^Main Conclusion/ }),
    ).toBeInTheDocument()
    // Dangling: rendered as its id, with nothing to click through to.
    expect(within(related).getByText('retired-concept')).toBeInTheDocument()
    expect(
      within(related).queryByRole('button', { name: /retired-concept/ }),
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
