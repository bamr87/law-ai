/**
 * The offline library, behaviourally (BL-20260903-07, BL-20260905-03).
 *
 * The reader, the contents rail, the outline and the search box shipped with
 * spec 048; the Articles/Concepts switcher and the shortcut gating that goes
 * with it landed later, in the concepts/library merge. Until the static site
 * had a test runner, all of it was covered only by the root suite's structural
 * checks — which prove the artifact is well formed, not that clicking a
 * cross-reference opens the article it names.
 *
 * The corpus is three fixture articles and two fixture concepts rather than
 * the shipped bundle, so an assertion here is about the component and not
 * about whichever article the library happens to hold this week.
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import Library from '@/components/Library'

vi.mock('@/lib/data', async () => {
  const f = await import('./fixtures')
  return f.libraryData()
})

vi.mock('@/lib/search', async () => {
  const f = await import('./fixtures')
  return { searchLibrary: f.librarySearch }
})

// The reader writes `#article-<id>` as it goes, so every test starts from a
// URL with no fragment rather than inheriting the last one's.
beforeEach(() => {
  window.history.replaceState(null, '', '/')
})

function rail(): HTMLElement {
  return screen.getByRole('navigation', { name: 'Library contents' })
}

function reader(): HTMLElement {
  return screen.getByRole('article')
}

function searchBox(): HTMLElement {
  return within(rail()).getByRole('searchbox')
}

function railTitles(): string[] {
  return within(rail())
    .getAllByRole('listitem')
    .map((li) => li.textContent ?? '')
}

describe('the contents rail', () => {
  it('opens on the head of the first track, not the first article by id', () => {
    // The article list is sorted by id, so an alphabetical default opened
    // "Conditional diagramming" on a reader who had not yet been told what
    // the exam is.
    render(<Library />)
    expect(reader()).toHaveAccessibleName('What the LSAT measures')
  })

  it('groups every article under its kind, in reading order', () => {
    render(<Library />)
    const eyebrows = within(rail())
      .getAllByText(/^(Orientation|Question type|Technique)$/)
      .map((el) => el.textContent)
    expect(eyebrows).toEqual(['Orientation', 'Question type', 'Technique'])
    expect(railTitles().join(' ')).toContain('The assumption family')
  })

  it('marks the article being read, and moves the mark when another is opened', () => {
    render(<Library />)
    fireEvent.click(within(rail()).getByText('The assumption family'))
    expect(reader()).toHaveAccessibleName('The assumption family')
    const current = within(rail()).getAllByRole('button', { current: true })
    expect(current).toHaveLength(1)
    expect(current[0]).toHaveTextContent('The assumption family')
  })

  it('narrows to one section, and to one reading track', () => {
    render(<Library />)
    fireEvent.click(within(rail()).getByRole('button', { name: 'Logic Games' }))
    expect(railTitles().join(' ')).toContain('Conditional diagramming')
    expect(railTitles().join(' ')).not.toContain('The assumption family')

    fireEvent.click(within(rail()).getByRole('button', { name: 'All sections' }))
    fireEvent.change(within(rail()).getByRole('combobox'), {
      target: { value: 'track-start' },
    })
    // A track's order is the curriculum, so it replaces the kind grouping.
    expect(railTitles()).toEqual([
      expect.stringContaining('What the LSAT measures'),
      expect.stringContaining('The assumption family'),
    ])
    expect(screen.getByText('Know what the exam asks before drilling it.'))
      .toBeInTheDocument()
  })
})

describe('the reader', () => {
  it('renders the article’s typed blocks and lists its headings', () => {
    render(<Library />)
    expect(within(reader()).getByRole('heading', { name: 'The three scored sections' }))
      .toBeInTheDocument()
    expect(reader()).toHaveTextContent('Start here, then read')

    const outline = within(reader()).getByRole('navigation', { name: 'On this page' })
    expect(within(outline).getByRole('link', { name: 'The three scored sections' }))
      .toHaveAttribute('href', '#three-sections')
  })

  it('follows a cross-reference to the article it names', () => {
    const onAnnounce = vi.fn()
    render(<Library onAnnounce={onAnnounce} />)
    fireEvent.click(
      within(reader()).getByRole('button', { name: 'the assumption family' }),
    )
    expect(reader()).toHaveAccessibleName('The assumption family')
    expect(onAnnounce).toHaveBeenCalledWith('Opened The assumption family')
    // A keyboard reader who followed the link lands in the new article.
    expect(document.activeElement).toBe(reader())
  })

  it('lists prerequisites and related articles, and opens them', () => {
    render(<Library />)
    fireEvent.click(within(rail()).getByText('The assumption family'))
    fireEvent.click(
      within(reader()).getByRole('button', { name: 'What the LSAT measures' }),
    )
    expect(reader()).toHaveAccessibleName('What the LSAT measures')
    // `related` and inbound links are merged, deduped, and never self-referential.
    const related = within(reader()).getByRole('heading', { name: 'Related' })
    expect(related.parentElement).toHaveTextContent('The assumption family')
    expect(related.parentElement).not.toHaveTextContent('What the LSAT measures')
  })

  it('remembers what has been read, in this browser', () => {
    render(<Library />)
    fireEvent.click(screen.getByRole('button', { name: 'Mark as read' }))
    expect(screen.getByRole('button', { name: '✓ Read' })).toBeInTheDocument()
    expect(window.localStorage.getItem('lsat-library-read')).toBe(
      JSON.stringify(['lib-orientation']),
    )
  })
})

describe('library search', () => {
  it('filters the rail down to what matched, and says when nothing did', () => {
    render(<Library />)
    fireEvent.change(searchBox(), { target: { value: 'diagram' } })
    expect(screen.getByText('1 result')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Conditional diagramming'))
    expect(reader()).toHaveAccessibleName('Conditional diagramming')

    fireEvent.change(searchBox(), { target: { value: 'xyzzy' } })
    expect(screen.getByText('0 results')).toBeInTheDocument()
    expect(screen.getByText(/Nothing matched/)).toBeInTheDocument()

    // A one-character query is not a search; the full contents come back.
    fireEvent.change(searchBox(), { target: { value: 'd' } })
    expect(screen.queryByText(/results?$/)).toBeNull()
    expect(railTitles().join(' ')).toContain('What the LSAT measures')
  })

  // Regression: issue #120. The chips lit up and `aria-pressed` went true, but
  // the search branch replaced the filtered rail wholesale with hits the filter
  // had never been shown — so the combination silently did half of what the
  // reader asked for, with nothing on screen to say so.
  it('composes the section chip with the search box', () => {
    render(<Library />)
    // "summary" is in every fixture article's summary: two LR, one LG.
    fireEvent.change(searchBox(), { target: { value: 'summary' } })
    expect(screen.getByText('3 results')).toBeInTheDocument()

    fireEvent.click(within(rail()).getByRole('button', { name: 'Logic Games' }))
    // The count is the filtered count, not the corpus-wide one.
    expect(screen.getByText('1 result')).toBeInTheDocument()
    const hits = railTitles().join(' ')
    expect(hits).toContain('Conditional diagramming')
    expect(hits).not.toContain('The assumption family')
    expect(hits).not.toContain('What the LSAT measures')

    // All sections restores the unfiltered hit list…
    fireEvent.click(within(rail()).getByRole('button', { name: 'All sections' }))
    expect(screen.getByText('3 results')).toBeInTheDocument()

    // …and clearing the query with a chip still selected falls back to the
    // filtered rail, which already worked and must not regress.
    fireEvent.click(within(rail()).getByRole('button', { name: 'Logic Games' }))
    fireEvent.change(searchBox(), { target: { value: '' } })
    expect(screen.queryByText(/results?$/)).toBeNull()
    expect(railTitles().join(' ')).toContain('Conditional diagramming')
    expect(railTitles().join(' ')).not.toContain('The assumption family')
  })

  it('leaves the article you are reading alone when a chip narrows the rail', () => {
    // Decided deliberately (issue #120): narrowing the contents must not yank
    // the page out from under a reader. The rail changes; the reader does not.
    render(<Library />)
    fireEvent.click(within(rail()).getByText('The assumption family'))
    expect(reader()).toHaveAccessibleName('The assumption family')

    fireEvent.click(within(rail()).getByRole('button', { name: 'Logic Games' }))
    expect(reader()).toHaveAccessibleName('The assumption family')
  })

  it('is reachable with / and left with Escape', () => {
    render(<Library />)
    fireEvent.keyDown(window, { key: '/' })
    expect(document.activeElement).toBe(searchBox())
    fireEvent.keyDown(searchBox(), { key: 'Escape' })
    expect(document.activeElement).not.toBe(searchBox())
  })

  it('steps through the visible list with J and K', () => {
    render(<Library />)
    fireEvent.keyDown(window, { key: 'j' })
    expect(reader()).toHaveAccessibleName('The assumption family')
    fireEvent.keyDown(window, { key: 'j' })
    expect(reader()).toHaveAccessibleName('Conditional diagramming')
    // Clamps rather than wrapping: the end of the contents is the end.
    fireEvent.keyDown(window, { key: 'j' })
    expect(reader()).toHaveAccessibleName('Conditional diagramming')
    fireEvent.keyDown(window, { key: 'k' })
    expect(reader()).toHaveAccessibleName('The assumption family')
  })

  it('steps through search results when a search is on screen', () => {
    render(<Library />)
    fireEvent.change(searchBox(), { target: { value: 'the' } })
    expect(screen.getByText('2 results')).toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'j' })
    expect(reader()).toHaveAccessibleName('The assumption family')
  })
})

describe('the Articles / Concepts switcher', () => {
  it('swaps the tabpanel and announces the view', () => {
    const onAnnounce = vi.fn()
    render(<Library onAnnounce={onAnnounce} />)
    const tabs = screen.getByRole('tablist', { name: 'Library views' })
    const articlesTab = within(tabs).getByRole('tab', { name: 'Long-form articles' })
    const conceptsTab = within(tabs).getByRole('tab', { name: 'Concept catalog' })
    expect(articlesTab).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tabpanel')).toHaveAttribute('id', 'lib-panel-articles')

    fireEvent.click(conceptsTab)
    expect(conceptsTab).toHaveAttribute('aria-selected', 'true')
    expect(articlesTab).toHaveAttribute('aria-selected', 'false')
    const panel = screen.getByRole('tabpanel')
    expect(panel).toHaveAttribute('id', 'lib-panel-concepts')
    expect(panel).toHaveAttribute('aria-labelledby', 'lib-view-concepts')
    expect(within(panel).getByRole('heading', { name: 'Necessary assumption' }))
      .toBeInTheDocument()
    expect(onAnnounce).toHaveBeenCalledWith('Concept catalog view')
    // The reader is gone, so the counts read the catalog instead.
    expect(screen.queryByRole('article')).toBeNull()
    // Both the library head and the catalog's own eyebrow now count concepts.
    expect(screen.getAllByText('2 recurring reasoning patterns')).toHaveLength(2)
  })

  it('disables the article bindings while the catalog is up', () => {
    // `/` and `j`/`k` aim at a search box and an ordered list that are not
    // mounted in the catalog; leaving them bound would also swallow the keys
    // from everything else on the page.
    render(<Library />)
    fireEvent.click(screen.getByRole('tab', { name: 'Concept catalog' }))
    const conceptSearch = screen.getByRole('searchbox')

    expect(fireEvent.keyDown(window, { key: '/' })).toBe(true)
    expect(document.activeElement).not.toBe(conceptSearch)
    expect(fireEvent.keyDown(window, { key: 'j' })).toBe(true)
    expect(fireEvent.keyDown(window, { key: 'k' })).toBe(true)
    expect(screen.getByRole('tabpanel')).toHaveAttribute('id', 'lib-panel-concepts')

    // Back on Articles they work again.
    fireEvent.click(screen.getByRole('tab', { name: 'Long-form articles' }))
    expect(fireEvent.keyDown(window, { key: 'j' })).toBe(false)
    expect(reader()).toHaveAccessibleName('The assumption family')
  })

  it('hands the reader back to Articles when a concept names one', () => {
    render(<Library />)
    fireEvent.click(screen.getByRole('tab', { name: 'Concept catalog' }))
    const card = screen.getByRole('heading', { name: 'Conditional chain' })
      .closest('li') as HTMLElement
    fireEvent.click(
      within(card).getByRole('button', { name: 'Conditional diagramming' }),
    )
    expect(screen.getByRole('tabpanel')).toHaveAttribute('id', 'lib-panel-articles')
    expect(reader()).toHaveAccessibleName('Conditional diagramming')
  })
})

describe('deep links', () => {
  it('opens the catalog on the concept a #catalog- link names', () => {
    // The cards have carried `id="catalog-<id>"` since the merge, but nothing
    // read the fragment, so such a URL opened cold landed on the reader —
    // the one thing the platform library could do that this one could not.
    window.history.replaceState(null, '', '#catalog-conditional-chain')
    render(<Library />)
    expect(screen.getByRole('tabpanel')).toHaveAttribute('id', 'lib-panel-concepts')
    const card = document.getElementById('catalog-conditional-chain')
    expect(card).toBeInTheDocument()
    expect(document.activeElement).toBe(card)
  })

  it('opens the reader on the article an #article- link names', () => {
    window.history.replaceState(null, '', '#article-lib-diagramming')
    render(<Library />)
    expect(reader()).toHaveAccessibleName('Conditional diagramming')
  })

  it('ignores a fragment that names nothing', () => {
    window.history.replaceState(null, '', '#article-not-a-real-id')
    render(<Library />)
    expect(reader()).toHaveAccessibleName('What the LSAT measures')
  })

  it('keeps the address bar on whatever is being read', () => {
    render(<Library />)
    expect(window.location.hash).toBe('#article-lib-orientation')
    fireEvent.click(within(rail()).getByText('Conditional diagramming'))
    expect(window.location.hash).toBe('#article-lib-diagramming')
  })

  it('follows a concept permalink', () => {
    render(<Library />)
    fireEvent.click(screen.getByRole('tab', { name: 'Concept catalog' }))
    // The permalink is a plain anchor, so the browser — not this component —
    // sets the fragment. jsdom does not navigate on click, so the effect of
    // the click is what gets simulated: a new fragment, then `hashchange`,
    // which is also what the back button does.
    expect(
      screen.getByRole('link', { name: 'Link to Conditional chain' }),
    ).toHaveAttribute('href', '#catalog-conditional-chain')

    window.history.replaceState(null, '', '#catalog-conditional-chain')
    fireEvent(window, new HashChangeEvent('hashchange'))
    expect(screen.getByRole('tabpanel')).toHaveAttribute('id', 'lib-panel-concepts')
    expect(document.activeElement).toBe(
      document.getElementById('catalog-conditional-chain'),
    )
  })

  it('switches back to the reader when the fragment changes to an article', () => {
    render(<Library />)
    fireEvent.click(screen.getByRole('tab', { name: 'Concept catalog' }))
    expect(screen.queryByRole('article')).toBeNull()

    window.history.replaceState(null, '', '#article-lib-assumptions')
    fireEvent(window, new HashChangeEvent('hashchange'))
    expect(screen.getByRole('tabpanel')).toHaveAttribute('id', 'lib-panel-articles')
    expect(reader()).toHaveAccessibleName('The assumption family')
  })
})
