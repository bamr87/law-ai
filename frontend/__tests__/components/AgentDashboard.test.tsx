import AgentDashboard from '@/components/AgentDashboard'
import { createNavStore } from '../support/urlNav'
import { server } from '@/mocks/server'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const nav = createNavStore('/agents')

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
  // Run filters live in the URL (BL-20260831-02); start every case clean.
  nav.reset()
  server.use(
    http.get(`${BASE}/api/agents`, () =>
      HttpResponse.json({
        count: 2,
        agents: [
          { name: 'LegalAnalyst', module: 'app.agents.crews.legal_analyst' },
          {
            name: 'PrecedentHunter',
            module: 'app.agents.crews.precedent_hunter',
          },
        ],
      }),
    ),
    http.get(`${BASE}/api/agents/runs`, () =>
      HttpResponse.json({
        count: 1,
        runs: [
          {
            trace_id: 't-1',
            agent: 'LegalAnalyst',
            type: 'agent_call',
            timestamp: '2026-04-29T12:00:00Z',
            latency_ms: 42,
          },
        ],
      }),
    ),
    http.get(`${BASE}/api/agents/backlog`, () =>
      HttpResponse.json({
        counts: { open: 3, claimed: 1, done: 5, total: 9 },
        open: [
          {
            id: 'BL-20260101-01',
            kind: 'feature',
            severity: 'high',
            title: 'Do thing',
          },
        ],
        claimed: [],
        done: [],
      }),
    ),
    http.get(`${BASE}/api/agents/specs`, () =>
      HttpResponse.json({
        count: 1,
        specs: [{ id: '003-agent-ops-dashboard', status: 'planned' }],
      }),
    ),
    // The autonomy cycle's own input (BL-20260527-07).
    http.get(`${BASE}/api/lsat/gaps`, () =>
      HttpResponse.json({
        limit: 3,
        count: 2,
        gaps: [
          {
            section: 'LR',
            concept: 'necessary-assumption',
            attempts: 12,
            correct: 4,
            accuracy: 0.3333,
          },
          {
            section: 'RC',
            concept: 'main-point',
            attempts: 6,
            correct: 3,
            accuracy: 0.5,
          },
        ],
      }),
    ),
  )
})

describe('AgentDashboard', () => {
  it('renders all four panel headings', async () => {
    render(<AgentDashboard />)
    await waitFor(() => {
      expect(screen.getByText('Registry')).toBeInTheDocument()
      expect(screen.getByText('Recent Runs')).toBeInTheDocument()
      expect(screen.getByText('Backlog')).toBeInTheDocument()
      expect(screen.getByText('Specs')).toBeInTheDocument()
    })
  })

  it('renders one card per registered agent (AC-6)', async () => {
    render(<AgentDashboard />)
    const cards = await screen.findAllByTestId('registry-card')
    expect(cards).toHaveLength(2)
    expect(cards[0]).toHaveTextContent('LegalAnalyst')
    expect(cards[1]).toHaveTextContent('PrecedentHunter')
  })

  it('shows backlog counts and recent run rows', async () => {
    render(<AgentDashboard />)
    await waitFor(() => {
      expect(screen.getByText(/Open: 3/)).toBeInTheDocument()
      expect(screen.getByText(/Claimed: 1/)).toBeInTheDocument()
      expect(screen.getByText(/Done: 5/)).toBeInTheDocument()
    })
    expect(screen.getByText('003-agent-ops-dashboard')).toBeInTheDocument()
  })

  it('reads the run filters out of the URL', async () => {
    // ?q= and ?type= make a filtered run list a link (BL-20260831-02).
    nav.reset('q=nomatch')
    render(<AgentDashboard />)
    await waitFor(() =>
      expect(screen.getByLabelText('Filter runs')).toHaveValue('nomatch'),
    )
    expect(screen.getByText(/No runs match "nomatch"/)).toBeInTheDocument()
  })

  it('replaces rather than pushes while a filter is being typed', async () => {
    render(<AgentDashboard />)
    await waitFor(() =>
      expect(screen.getByLabelText('Filter runs')).toBeInTheDocument(),
    )
    nav.reset()
    fireEvent.change(screen.getByLabelText('Filter runs'), {
      target: { value: 'legal' },
    })
    // Instant in the box…
    expect(screen.getByLabelText('Filter runs')).toHaveValue('legal')
    // …and in the URL a beat later, without a history entry per keystroke.
    await waitFor(() => expect(nav.replace).toHaveBeenCalled())
    expect(nav.push).not.toHaveBeenCalled()
    expect(nav.hrefs[nav.hrefs.length - 1]).toBe('/agents?q=legal')
  })

  it('shows the next autonomy target from the gap analysis (BL-20260527-07)', async () => {
    render(<AgentDashboard />)
    const card = await screen.findByTestId('next-autonomy-target')
    expect(card).toHaveTextContent('Next autonomy target')
    // Top row: what tonight's cycle will actually draft.
    expect(card).toHaveTextContent('necessary-assumption')
    expect(card).toHaveTextContent('12 attempts')
    expect(card).toHaveTextContent('33% accuracy')
    // The rest are collapsed behind a disclosure, not lost.
    expect(card).toHaveTextContent('1 more measured gap')
    expect(
      screen.getByRole('link', { name: /Open LSAT authoring/ }),
    ).toHaveAttribute('href', '/lsat?tab=authoring')
  })

  it('says so when the gap analysis is empty', async () => {
    server.use(
      http.get(`${BASE}/api/lsat/gaps`, () =>
        HttpResponse.json({ limit: 3, count: 0, gaps: [] }),
      ),
    )
    render(<AgentDashboard />)
    const card = await screen.findByTestId('next-autonomy-target')
    expect(card).toHaveTextContent(/No measured gaps yet/)
  })

  // BL-20260831-07: both modals were hand-rolled dialogs with no focus
  // management. They now use the shell's `useFocusTrap`, like the command
  // palette and the shortcut sheet.
  describe('modal focus management', () => {
    async function openLaunchModal() {
      render(<AgentDashboard />)
      const runButtons = await screen.findAllByRole('button', { name: 'Run' })
      const trigger = runButtons[0]
      trigger.focus()
      fireEvent.click(trigger)
      const dialog = await screen.findByRole('dialog', {
        name: /Run LegalAnalyst/,
      })
      return { dialog, trigger }
    }

    it('moves focus into the launch dialog when it opens', async () => {
      const { dialog } = await openLaunchModal()
      await waitFor(() =>
        expect(dialog).toContainElement(document.activeElement as HTMLElement),
      )
    })

    it('closes the launch dialog on Escape', async () => {
      const { dialog } = await openLaunchModal()
      fireEvent.keyDown(dialog, { key: 'Escape' })
      await waitFor(() =>
        expect(
          screen.queryByRole('dialog', { name: /Run LegalAnalyst/ }),
        ).not.toBeInTheDocument(),
      )
    })

    it('returns focus to the launching button after close', async () => {
      const { dialog, trigger } = await openLaunchModal()
      fireEvent.keyDown(dialog, { key: 'Escape' })
      await waitFor(() => expect(document.activeElement).toBe(trigger))
    })

    it('traps Tab inside the dialog', async () => {
      const { dialog } = await openLaunchModal()
      const focusable = dialog.querySelectorAll<HTMLElement>(
        'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])',
      )
      const last = focusable[focusable.length - 1]
      last.focus()
      fireEvent.keyDown(dialog, { key: 'Tab' })
      expect(dialog).toContainElement(document.activeElement as HTMLElement)
      expect(document.activeElement).toBe(focusable[0])
    })

    it('traps the run-detail dialog too', async () => {
      server.use(
        http.get(`${BASE}/api/agents/runs/t-1`, () =>
          HttpResponse.json({ trace_id: 't-1', count: 0, events: [] }),
        ),
      )
      render(<AgentDashboard />)
      fireEvent.click(await screen.findByLabelText('Show run details'))
      const drill = await screen.findByRole('button', {
        name: /View all related events/,
      })
      drill.focus()
      fireEvent.click(drill)
      const dialog = await screen.findByRole('dialog', { name: 'Run details' })
      await waitFor(() =>
        expect(dialog).toContainElement(document.activeElement as HTMLElement),
      )
      fireEvent.keyDown(dialog, { key: 'Escape' })
      await waitFor(() =>
        expect(
          screen.queryByRole('dialog', { name: 'Run details' }),
        ).not.toBeInTheDocument(),
      )
      expect(document.activeElement).toBe(drill)
    })
  })

  it('surfaces panel-level errors without crashing the page', async () => {
    server.use(
      http.get(`${BASE}/api/agents/runs`, () =>
        HttpResponse.json({ detail: 'boom' }, { status: 500 }),
      ),
    )
    render(<AgentDashboard />)
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/Failed to load/)
    })
    // Other panels still render
    expect(screen.getByText('Registry')).toBeInTheDocument()
  })

  // --- BL-20260429-16: push replaces polling, but only when it connects ---

  it('falls back to polling where there is no WebSocket', async () => {
    // jsdom has none, which is exactly the degraded path the socket client is
    // written for: the dashboard must still say it is auto-refreshing.
    render(<AgentDashboard />)
    await waitFor(() => {
      expect(screen.getByText(/Auto-refresh every 5s/)).toBeInTheDocument()
    })
  })

  it('says it is live once the push channel connects', async () => {
    class ReadySocket {
      onmessage: ((e: { data: string }) => void) | null = null
      onerror: (() => void) | null = null
      onclose: (() => void) | null = null
      close = vi.fn()
      constructor() {
        setTimeout(() => {
          this.onmessage?.({
            data: JSON.stringify({ type: 'ready', channel: 'ops-dashboard' }),
          })
        }, 0)
      }
    }
    vi.stubGlobal('WebSocket', ReadySocket as unknown as typeof WebSocket)

    render(<AgentDashboard />)
    await waitFor(() => {
      expect(screen.getByText(/updates pushed as they happen/)).toBeInTheDocument()
    })
    vi.unstubAllGlobals()
  })
})

// --- Spec 008 AC-6, as amended by BL-20260430-07 ---
//
// The key used to be `NEXT_PUBLIC_AGENT_API_KEY`, read in the browser and set
// on every request — which put it in the bundle. It is now attached by the
// same-origin proxy route from a server-only `AGENT_API_KEY`, so the *client*
// must send no credential at all, whatever is in the environment. Asserting
// the absence is the point: a regression here is a leaked key.

describe('AgentDashboard auth header (spec 008, BL-20260430-07)', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  function captureKeys(seen: (string | null)[]) {
    const capture =
      (body: Record<string, unknown>): Parameters<typeof http.get>[1] =>
      ({ request }) => {
        seen.push(request.headers.get('x-api-key'))
        return HttpResponse.json(body)
      }
    server.use(
      http.get(`${BASE}/api/agents`, capture({ count: 0, agents: [] })),
      http.get(`${BASE}/api/agents/runs`, capture({ count: 0, runs: [] })),
      http.get(
        `${BASE}/api/agents/backlog`,
        capture({
          counts: { open: 0, claimed: 0, done: 0, total: 0 },
          open: [],
          claimed: [],
          done: [],
        }),
      ),
      http.get(`${BASE}/api/agents/specs`, capture({ count: 0, specs: [] })),
    )
  }

  it('sends no X-API-Key from the browser', async () => {
    const seen: (string | null)[] = []
    captureKeys(seen)
    render(<AgentDashboard />)
    await waitFor(() => expect(seen.length).toBe(4))
    for (const value of seen) expect(value).toBeNull()
  })

  it('still sends none when a public key env var is somehow present', async () => {
    // The variable is gone from `.env.example` and from `api.ts`; a stale one
    // in someone's shell must not resurrect the leak.
    vi.stubEnv('NEXT_PUBLIC_AGENT_API_KEY', 's3cret')
    const seen: (string | null)[] = []
    captureKeys(seen)
    render(<AgentDashboard />)
    await waitFor(() => expect(seen.length).toBe(4))
    for (const value of seen) expect(value).toBeNull()
  })
})
