import KnowledgeGraph from '@/components/KnowledgeGraph'
import { createNavStore } from '../support/urlNav'
import { server } from '@/mocks/server'
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// Cytoscape touches the DOM with layouts that jsdom doesn't implement;
// stub the dynamic import so we can assert structural rendering only.
// `on` is part of the surface GraphViewer uses (node taps drive the sidebar
// inspector, BL-20260429-23), so the stub has to answer it.
const cyTapHandlers: ((evt: { target: { id: () => string } }) => void)[] = []
vi.mock('cytoscape', () => ({
  default: () => ({
    destroy: vi.fn(),
    on: (
      _event: string,
      _selector: string,
      handler: (evt: { target: { id: () => string } }) => void,
    ) => {
      cyTapHandlers.push(handler)
    },
  }),
}))

const nav = createNavStore('/graph')

vi.mock('next/navigation', async () => {
  const { useSyncExternalStore } = await import('react')
  return {
    usePathname: () => nav.path,
    useSearchParams: () =>
      useSyncExternalStore(nav.subscribe, nav.read, nav.read),
    useRouter: () => ({ push: nav.push, replace: nav.replace }),
  }
})

const BASE = 'http://localhost:8000'

beforeEach(() => {
  // The selected case lives in the URL (BL-20260831-02); start every case
  // clean so one test's selection cannot seed the next.
  nav.reset()
  server.use(
    http.get(`${BASE}/api/graph/stats`, () =>
      HttpResponse.json({
        available: true,
        cases: 7,
        citations: 12,
        cites_edges: 4,
      }),
    ),
    http.get(`${BASE}/api/graph/cases`, () =>
      HttpResponse.json({
        available: true,
        count: 2,
        cases: [
          {
            id: 'case-a',
            title: 'Roe v. Wade',
            court: 'Supreme Court',
            decided_at: '1973-01-22',
          },
          {
            id: 'case-b',
            title: 'Brown v. Board',
            court: 'Supreme Court',
            decided_at: '1954-05-17',
          },
        ],
      }),
    ),
    http.get(`${BASE}/api/graph/path`, ({ request }) => {
      const url = new URL(request.url)
      const from = url.searchParams.get('from') as string
      const to = url.searchParams.get('to') as string
      if (to === 'case-nowhere') {
        return HttpResponse.json({
          available: true,
          found: false,
          hops: 0,
          nodes: [],
          edges: [],
        })
      }
      return HttpResponse.json({
        available: true,
        found: true,
        hops: 1,
        nodes: [
          { data: { id: from, label: 'From', type: 'Case', on_path: true } },
          { data: { id: to, label: 'To', type: 'Case', on_path: true } },
        ],
        edges: [
          {
            data: {
              id: `cites:${from}->${to}`,
              source: from,
              target: to,
              type: 'CITES',
              on_path: true,
            },
          },
        ],
      })
    }),
    http.get(`${BASE}/api/graph/neighborhood/:id`, ({ params }) =>
      HttpResponse.json({
        available: true,
        nodes: [
          {
            data: {
              id: params.id as string,
              label: 'Selected',
              type: 'Case',
              court: 'Supreme Court',
            },
          },
          {
            data: {
              id: 'cit:410 us 113',
              label: '410 U.S. 113',
              type: 'Citation',
            },
          },
        ],
        edges: [
          {
            data: {
              id: `hc:${params.id as string}->cit:410 us 113`,
              source: params.id as string,
              target: 'cit:410 us 113',
              type: 'HAS_CITATION',
            },
          },
        ],
      }),
    ),
  )
})

describe('KnowledgeGraph', () => {
  it('renders Cases + Neighborhood headings and stats (AC-6)', async () => {
    render(<KnowledgeGraph />)
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Cases' })).toBeInTheDocument()
      expect(
        screen.getByRole('heading', { name: 'Neighborhood' }),
      ).toBeInTheDocument()
    })
    // Stats strip values
    await waitFor(() => {
      expect(screen.getByText('7')).toBeInTheDocument()
      expect(screen.getByText('12')).toBeInTheDocument()
    })
    // Cytoscape canvas mounts
    expect(screen.getByTestId('graph-canvas')).toBeInTheDocument()
  })

  it('lists cases from the API and auto-selects the first', async () => {
    render(<KnowledgeGraph />)
    // Scoped to the picker: case titles also appear as options in the
    // precedent-chain select (BL-20260429-22).
    const list = await screen.findByTestId('case-list')
    await waitFor(() => {
      expect(within(list).getAllByText('Roe v. Wade').length).toBeGreaterThan(0)
      expect(within(list).getByText('Brown v. Board')).toBeInTheDocument()
    })
    // Selected case header shows neighborhood node count
    await waitFor(() => {
      expect(screen.getByText(/2$/, { selector: 'span' })).toBeInTheDocument()
    })
  })

  it('selects the case the URL names instead of the first one', async () => {
    // A shared link must land on the case it names (BL-20260831-02).
    nav.reset('case=case-b')
    render(<KnowledgeGraph />)
    const list = await screen.findByTestId('case-list')
    await waitFor(() =>
      expect(within(list).getByText('Brown v. Board')).toBeInTheDocument(),
    )
    // The URL's case is the selected row, not the first one in the list.
    const selected = within(list)
      .getByText('Brown v. Board')
      .closest('button') as HTMLElement
    expect(selected.className).toContain('bg-blue-500/10')
    expect(nav.read().get('case')).toBe('case-b')
    // No auto-select ran over the top of it.
    expect(nav.push).not.toHaveBeenCalled()
  })

  it('replaces rather than pushes the auto-selected first case', async () => {
    // Nobody *chose* the first case, so it must not become a history entry
    // (BL-20260831-02). Pushing it made Back inside the screen land back on
    // `/graph` with nothing selected and nothing to re-select it — a dead end
    // the reader had to press Back twice to leave.
    render(<KnowledgeGraph />)
    const list = await screen.findByTestId('case-list')
    await waitFor(() => expect(nav.read().get('case')).toBe('case-a'))
    expect(nav.replace).toHaveBeenCalled()
    expect(nav.push).not.toHaveBeenCalled()
    // Exactly one navigation, and it did not add to history.
    expect(nav.hrefs).toEqual(['/graph?case=case-a'])
    // The auto-selected case really is the selected row.
    const selected = within(list)
      .getAllByText('Roe v. Wade')[0]
      .closest('button') as HTMLElement
    expect(selected.className).toContain('bg-blue-500/10')
  })

  it('puts a chosen case in the URL so Back walks the cases', async () => {
    render(<KnowledgeGraph />)
    const list = await screen.findByTestId('case-list')
    await waitFor(() =>
      expect(within(list).getByText('Brown v. Board')).toBeInTheDocument(),
    )
    nav.reset()
    fireEvent.click(within(list).getByText('Brown v. Board'))
    expect(nav.push).toHaveBeenCalled()
    expect(nav.hrefs[nav.hrefs.length - 1]).toBe('/graph?case=case-b')
  })

  it('shows a banner when Neo4j is unavailable', async () => {
    server.use(
      http.get(`${BASE}/api/graph/stats`, () =>
        HttpResponse.json({
          available: false,
          cases: 0,
          citations: 0,
          cites_edges: 0,
        }),
      ),
      http.get(`${BASE}/api/graph/cases`, () =>
        HttpResponse.json({ available: false, count: 0, cases: [] }),
      ),
    )
    render(<KnowledgeGraph />)
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(
        /Neo4j is not reachable/,
      )
    })
  })
})

// --- BL-20260429-22: precedent chain ---

describe('KnowledgeGraph precedent chain', () => {
  it('asks for no chain until a second case is chosen', async () => {
    const seen: string[] = []
    server.use(
      http.get(`${BASE}/api/graph/path`, ({ request }) => {
        seen.push(request.url)
        return HttpResponse.json({
          available: true,
          found: false,
          hops: 0,
          nodes: [],
          edges: [],
        })
      }),
    )
    render(<KnowledgeGraph />)
    await screen.findByTestId('case-list')
    await waitFor(() =>
      expect(screen.getByLabelText('Precedent chain to')).toBeInTheDocument(),
    )
    expect(seen).toHaveLength(0)
    // The picker never offers the already-selected case as its own endpoint.
    const select = screen.getByLabelText(
      'Precedent chain to',
    ) as HTMLSelectElement
    const values = Array.from(select.options).map((o) => o.value)
    expect(values).toEqual(['', 'case-b'])
  })

  it('highlights the chain and reports the hop count', async () => {
    render(<KnowledgeGraph />)
    await screen.findByTestId('case-list')
    const select = await screen.findByLabelText('Precedent chain to')
    fireEvent.change(select, { target: { value: 'case-b' } })

    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent(
        'Chain found: 1 hop',
      ),
    )
    // The chain's extra node is merged into the canvas alongside the
    // neighborhood's two, and the legend gains its key.
    await waitFor(() => expect(screen.getByText('3 nodes')).toBeInTheDocument())
    expect(screen.getByText('Precedent chain')).toBeInTheDocument()
  })

  it('says so when there is no chain within the hop bound', async () => {
    server.use(
      http.get(`${BASE}/api/graph/cases`, () =>
        HttpResponse.json({
          available: true,
          count: 2,
          cases: [
            {
              id: 'case-a',
              title: 'Roe v. Wade',
              court: 'SC',
              decided_at: null,
            },
            {
              id: 'case-nowhere',
              title: 'Unrelated',
              court: 'SC',
              decided_at: null,
            },
          ],
        }),
      ),
    )
    render(<KnowledgeGraph />)
    await screen.findByTestId('case-list')
    const select = await screen.findByLabelText('Precedent chain to')
    fireEvent.change(select, { target: { value: 'case-nowhere' } })
    await waitFor(() =>
      expect(screen.getByRole('status')).toHaveTextContent(
        'No chain within 6 hops',
      ),
    )
    expect(screen.queryByText('Precedent chain')).not.toBeInTheDocument()
  })

  it('puts the second endpoint in the URL and clears it again', async () => {
    render(<KnowledgeGraph />)
    await screen.findByTestId('case-list')
    const select = await screen.findByLabelText('Precedent chain to')
    fireEvent.change(select, { target: { value: 'case-b' } })
    await waitFor(() => expect(nav.read().get('compare')).toBe('case-b'))

    fireEvent.click(await screen.findByRole('button', { name: 'Clear chain' }))
    await waitFor(() => expect(nav.read().get('compare')).toBeNull())
  })
})

// --- BL-20260429-23: picker filters + sidebar inspector ---

describe('KnowledgeGraph filters and inspector', () => {
  it('sends court and date filters to the API', async () => {
    const seen: URL[] = []
    server.use(
      http.get(`${BASE}/api/graph/cases`, ({ request }) => {
        seen.push(new URL(request.url))
        return HttpResponse.json({
          available: true,
          count: 1,
          cases: [
            {
              id: 'case-a',
              title: 'Roe v. Wade',
              court: 'Supreme Court',
              decided_at: '1973-01-22',
            },
          ],
        })
      }),
    )
    render(<KnowledgeGraph />)
    await screen.findByTestId('case-list')

    fireEvent.change(screen.getByLabelText('Court'), {
      target: { value: 'Supreme Court' },
    })
    fireEvent.change(screen.getByLabelText('Decided from'), {
      target: { value: '1970-01-01' },
    })
    fireEvent.change(screen.getByLabelText('Decided to'), {
      target: { value: '1980-12-31' },
    })

    await waitFor(() => {
      const last = seen[seen.length - 1]
      expect(last.searchParams.get('court')).toBe('Supreme Court')
      expect(last.searchParams.get('decided_from')).toBe('1970-01-01')
      expect(last.searchParams.get('decided_to')).toBe('1980-12-31')
    })
  })

  it('derives the court options from the loaded cases', async () => {
    render(<KnowledgeGraph />)
    await screen.findByTestId('case-list')
    const select = (await screen.findByLabelText('Court')) as HTMLSelectElement
    await waitFor(() =>
      expect(Array.from(select.options).map((o) => o.value)).toEqual([
        '',
        'Supreme Court',
      ]),
    )
  })

  it('offers courts from the whole corpus, not just the loaded page', async () => {
    // BL-20260905-89: /api/graph/courts seeds the dropdown, so a court with
    // no case on the first page is still selectable.
    server.use(
      http.get(`${BASE}/api/graph/courts`, () =>
        HttpResponse.json({
          available: true,
          count: 2,
          courts: [
            { court: 'Supreme Court', count: 12 },
            { court: '10th Cir.', count: 3 },
          ],
        }),
      ),
    )
    render(<KnowledgeGraph />)
    await screen.findByTestId('case-list')
    const select = (await screen.findByLabelText('Court')) as HTMLSelectElement
    await waitFor(() =>
      expect(Array.from(select.options).map((o) => o.value)).toEqual([
        '',
        '10th Cir.',
        'Supreme Court',
      ]),
    )
  })

  it('falls back to the loaded cases when the court feed is down', async () => {
    server.use(
      http.get(`${BASE}/api/graph/courts`, () =>
        HttpResponse.json({ available: false, courts: [], count: 0 }),
      ),
    )
    render(<KnowledgeGraph />)
    await screen.findByTestId('case-list')
    const select = (await screen.findByLabelText('Court')) as HTMLSelectElement
    await waitFor(() =>
      expect(Array.from(select.options).map((o) => o.value)).toEqual([
        '',
        'Supreme Court',
      ]),
    )
  })

  it('resets every filter at once', async () => {
    render(<KnowledgeGraph />)
    await screen.findByTestId('case-list')
    fireEvent.change(screen.getByLabelText('Court'), {
      target: { value: 'Supreme Court' },
    })
    const reset = await screen.findByRole('button', { name: 'Reset filters' })
    fireEvent.click(reset)
    await waitFor(() =>
      expect((screen.getByLabelText('Court') as HTMLSelectElement).value).toBe(
        '',
      ),
    )
  })

  it('inspects the selected case with its full properties and source link', async () => {
    server.use(
      http.get(`${BASE}/api/graph/neighborhood/:id`, ({ params }) =>
        HttpResponse.json({
          available: true,
          nodes: [
            {
              data: {
                id: params.id as string,
                label: 'Selected',
                type: 'Case',
                title: 'Roe v. Wade',
                court: 'Supreme Court',
                decided_at: '1973-01-22',
                source: 'courtlistener',
                source_url: 'https://example.test/roe',
                confidence: 0.92,
              },
            },
          ],
          edges: [],
        }),
      ),
    )
    render(<KnowledgeGraph />)
    const inspector = await screen.findByTestId('node-inspector')
    await waitFor(() =>
      expect(within(inspector).getByText('courtlistener')).toBeInTheDocument(),
    )
    expect(within(inspector).getByText('Decided')).toBeInTheDocument()
    expect(within(inspector).getByText('1973-01-22')).toBeInTheDocument()
    expect(within(inspector).getByText('0.92')).toBeInTheDocument()
    const link = within(inspector).getByRole('link', { name: /Open source/ })
    expect(link).toHaveAttribute('href', 'https://example.test/roe')
    expect(link).toHaveAttribute('target', '_blank')
    // The raw URL is a link, not another key/value row.
    expect(
      within(inspector).queryByText('https://example.test/roe'),
    ).not.toBeInTheDocument()
  })

  it('moves the inspector to the node tapped on the canvas', async () => {
    render(<KnowledgeGraph />)
    await screen.findByTestId('node-inspector')
    await waitFor(() => expect(cyTapHandlers.length).toBeGreaterThan(0))
    const tap = cyTapHandlers[cyTapHandlers.length - 1]
    tap({ target: { id: () => 'cit:410 us 113' } })
    const inspector = await screen.findByTestId('node-inspector')
    await waitFor(() =>
      expect(within(inspector).getByText('Citation')).toBeInTheDocument(),
    )
    expect(within(inspector).getByText('cit:410 us 113')).toBeInTheDocument()
  })
})

// --- BL-20260831-12: traversing CITES edges without a mouse ---

describe('KnowledgeGraph citation traversal', () => {
  /** A neighborhood with one outgoing CITES, one incoming, and a Citation. */
  const withCites = () =>
    server.use(
      http.get(`${BASE}/api/graph/neighborhood/:id`, ({ params }) => {
        const id = params.id as string
        return HttpResponse.json({
          available: true,
          nodes: [
            { data: { id, label: 'Selected', type: 'Case' } },
            {
              data: {
                id: 'case-b',
                title: 'Brown v. Board',
                label: 'Brown v. Board',
                type: 'Case',
                court: 'Supreme Court',
              },
            },
            {
              data: {
                id: 'case-c',
                title: 'Casey v. PP',
                label: 'Casey v. PP',
                type: 'Case',
              },
            },
            {
              data: {
                id: 'cit:410 us 113',
                label: '410 U.S. 113',
                type: 'Citation',
              },
            },
          ],
          edges: [
            {
              data: {
                id: `cites:${id}->case-b`,
                source: id,
                target: 'case-b',
                type: 'CITES',
              },
            },
            {
              data: {
                id: `cites:case-c->${id}`,
                source: 'case-c',
                target: id,
                type: 'CITES',
              },
            },
            {
              data: {
                id: `hc:${id}->cit:410 us 113`,
                source: id,
                target: 'cit:410 us 113',
                type: 'HAS_CITATION',
              },
            },
          ],
        })
      }),
    )

  it('lists cited and citing cases as buttons, grouped by direction', async () => {
    withCites()
    render(<KnowledgeGraph />)
    const panel = await screen.findByTestId('cites-traversal')
    const cites = await within(panel).findByRole('list', {
      name: 'This case cites',
    })
    const citedBy = within(panel).getByRole('list', { name: 'Cited by' })
    expect(
      within(cites).getByRole('button', { name: /Brown v. Board/ }),
    ).toBeInTheDocument()
    expect(
      within(citedBy).getByRole('button', { name: /Casey v. PP/ }),
    ).toBeInTheDocument()
    // A HAS_CITATION neighbour is not a traversal target.
    expect(
      within(panel).queryByRole('button', { name: /410 U\.S\. 113/ }),
    ).toBeNull()
  })

  it('follows an edge to the neighbouring case when a row is activated', async () => {
    withCites()
    render(<KnowledgeGraph />)
    const panel = await screen.findByTestId('cites-traversal')
    // The panel mounts before its neighbour rows arrive, so the button has to
    // be awaited: a sync query here races the fetch on a slower runner.
    fireEvent.click(
      await within(panel).findByRole('button', { name: /Brown v. Board/ }),
    )
    // Selection is URL state, so the trail is linkable and Back unwinds it.
    await waitFor(() =>
      expect(nav.hrefs[nav.hrefs.length - 1]).toContain('case=case-b'),
    )
  })

  it('says so when an edge direction has no neighbours', async () => {
    render(<KnowledgeGraph />) // default fixture: HAS_CITATION only
    const panel = await screen.findByTestId('cites-traversal')
    expect(panel).toHaveTextContent(
      /No outgoing citations in this neighborhood/,
    )
    expect(panel).toHaveTextContent(/No citing cases in this neighborhood/)
  })

  it('leaves the canvas reachable by keyboard', async () => {
    render(<KnowledgeGraph />)
    const canvas = await screen.findByTestId('graph-canvas')
    expect(canvas).toHaveAttribute('tabindex', '0')
    expect(canvas.getAttribute('aria-label')).toMatch(/Arrow keys step through/)
  })
})

// --- BL-20260803-03: the legend has to name what the node size measures ---

describe('KnowledgeGraph citation-count legend', () => {
  it('labels node size as litigation frequency, never importance', async () => {
    render(<KnowledgeGraph />)
    const legend = await screen.findByTestId('legend-citation-size')
    expect(legend).toHaveTextContent(/litigation frequency/i)
    expect(legend).toHaveTextContent(/not importance/i)
    // The tooltip carries the §13 caveat in full.
    expect(legend.getAttribute('title')).toMatch(
      /not legal correctness or authority/i,
    )
  })
})
