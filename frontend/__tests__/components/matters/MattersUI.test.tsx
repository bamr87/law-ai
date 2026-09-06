import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'

import AccountData from '@/components/matters/AccountData'
import MatterList from '@/components/matters/MatterList'
import MatterResearch from '@/components/matters/MatterResearch'
import MatterWorkspace from '@/components/matters/MatterWorkspace'
import StudyFromMatter from '@/components/lsat/StudyFromMatter'
import TaskCalendar from '@/components/matters/TaskCalendar'
import { server } from '@/mocks/server'

vi.mock('next/link', () => ({
  default: ({
    children,
    href,
    ...rest
  }: {
    children: React.ReactNode
    href: string
  }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}))

const MATTER = {
  id: 7,
  slug: 'smith-lease',
  name: 'Smith lease dispute',
  stage: 'research',
  issue_tags: ['landlord-tenant'],
  jurisdiction: 'co',
  updated_at: '2026-09-01T00:00:00Z',
}

describe('MatterList', () => {
  it('invites a sign-in rather than showing an error', async () => {
    server.use(
      http.get('*/api/matters', () =>
        HttpResponse.json({ detail: 'sign in' }, { status: 401 }),
      ),
    )
    render(<MatterList />)
    expect(
      await screen.findByText(/Matters are per-account/),
    ).toBeInTheDocument()
  })

  it('lists matters with their stage and tags', async () => {
    server.use(
      http.get('*/api/matters', () =>
        HttpResponse.json({ count: 1, matters: [MATTER] }),
      ),
    )
    render(<MatterList />)
    expect(await screen.findByText('Smith lease dispute')).toBeInTheDocument()
    expect(screen.getByText('research')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Smith lease dispute' })).toHaveAttribute(
      'href',
      '/matters/smith-lease',
    )
  })
})

describe('TaskCalendar', () => {
  const CALENDAR = {
    window_days: 30,
    generated_at: '2026-09-06T12:00:00Z',
    overdue: [
      {
        id: 1,
        title: 'File answer',
        detail: '',
        due_at: '2026-09-01T00:00:00Z',
        status: 'open' as const,
        source_artifact_id: null,
        reminded_at: null,
        completed_at: null,
        created_at: null,
        matter_slug: 'smith-lease',
        matter_name: 'Smith lease dispute',
        overdue_days: 5,
      },
    ],
    today: [],
    upcoming: [],
    count: 1,
  }

  it('leads with overdue work and says who it belongs to', async () => {
    server.use(
      http.get('*/api/matters/calendar', () => HttpResponse.json(CALENDAR)),
    )
    render(<TaskCalendar />)
    expect(await screen.findByText('Overdue')).toBeInTheDocument()
    expect(screen.getByText('File answer')).toBeInTheDocument()
    expect(screen.getByText(/Smith lease dispute/)).toBeInTheDocument()
    // Spec 036 NG1: the surface says the dates are the user's own.
    expect(
      screen.getByText(/does not compute filing deadlines/),
    ).toBeInTheDocument()
  })

  it('completing a task patches the matter it belongs to', async () => {
    const patched: string[] = []
    server.use(
      http.get('*/api/matters/calendar', () => HttpResponse.json(CALENDAR)),
      http.patch('*/api/matters/smith-lease/tasks/1', async ({ request }) => {
        patched.push(String((await request.json()) && 'done'))
        return HttpResponse.json({ ...CALENDAR.overdue[0], status: 'done' })
      }),
    )
    render(<TaskCalendar />)
    fireEvent.click(await screen.findByRole('button', { name: 'Done' }))
    await waitFor(() => expect(patched).toHaveLength(1))
  })

  it('renders nothing at all when the caller is signed out', async () => {
    server.use(
      http.get('*/api/matters/calendar', () =>
        HttpResponse.json({ detail: 'sign in' }, { status: 401 }),
      ),
    )
    const { container } = render(<TaskCalendar />)
    await waitFor(() => expect(container.textContent).toBe(''))
  })
})

describe('StudyFromMatter', () => {
  it('ranks the matter’s concepts and links each into the drill', async () => {
    server.use(
      http.get('*/api/matters/smith-lease/study-plan', () =>
        HttpResponse.json({
          matter: { slug: 'smith-lease', name: 'Smith', issue_tags: ['x'] },
          covered_tags: ['landlord-tenant'],
          unmapped_tags: ['quantum-meruit'],
          concepts: [
            {
              concept_id: 'conditional-reasoning',
              name: 'Conditional Reasoning',
              sections: ['LR'],
              summary: 'If-then.',
              from_tags: ['landlord-tenant'],
              why: 'Notice rules are conditionals.',
              attempts: 0,
              accuracy: null,
              status: 'unpractised',
              articles: ['a1'],
              drills: ['lr-1', 'lr-2'],
            },
          ],
        }),
      ),
    )
    render(<StudyFromMatter slug="smith-lease" />)
    expect(await screen.findByText('Conditional Reasoning')).toBeInTheDocument()
    expect(screen.getByText('not practised')).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: 'Conditional Reasoning' }),
    ).toHaveAttribute('href', '/lsat?concept=conditional-reasoning')
    expect(screen.getByText(/No mapping yet for/)).toBeInTheDocument()
  })

  it('says so when no material maps to the tags', async () => {
    server.use(
      http.get('*/api/matters/x/study-plan', () =>
        HttpResponse.json({
          matter: { slug: 'x', name: 'X', issue_tags: ['admiralty'] },
          concepts: [],
          unmapped_tags: ['admiralty'],
          covered_tags: [],
        }),
      ),
    )
    render(<StudyFromMatter slug="x" />)
    expect(await screen.findByText(/No study material maps/)).toBeInTheDocument()
  })
})

describe('AccountData', () => {
  it('shows the export bundle in the page', async () => {
    server.use(
      http.get('*/api/account/export', () =>
        HttpResponse.json({ bundle_version: 1, matters: [] }),
      ),
    )
    render(<AccountData />)
    fireEvent.click(screen.getByRole('button', { name: 'Build export' }))
    expect(await screen.findByText(/bundle_version/)).toBeInTheDocument()
  })

  it('keeps deletion disabled until the username is retyped', async () => {
    render(<AccountData />)
    const button = screen.getByRole('button', { name: 'Delete account' })
    expect(button).toBeDisabled()
    fireEvent.change(screen.getByLabelText(/Type your username/), {
      target: { value: 'ada' },
    })
    expect(button).toBeEnabled()
  })

  it('surfaces the backend’s own wording when deletion is refused', async () => {
    server.use(
      http.post('*/api/account/delete', () =>
        HttpResponse.json(
          { detail: 'confirm_username must match the signed-in username' },
          { status: 400 },
        ),
      ),
    )
    render(<AccountData />)
    fireEvent.change(screen.getByLabelText(/Type your username/), {
      target: { value: 'nope' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Delete account' }))
    expect(
      await screen.findByText(/confirm_username must match/),
    ).toBeInTheDocument()
  })
})

// --- BL-20260906-95: research scoped to the matter on screen ---

const IRAC_REPLY = {
  id: 'analysis-matter-1',
  timestamp: '2026-09-06T00:00:00Z',
  latency_ms: 900,
  confidence: 0.81,
  requires_human_review: false,
  irac: {
    issue: 'Whether notice was properly served.',
    rule: 'Notice must be in writing.',
    application: 'The landlord posted it.',
    conclusion: 'Service was defective.',
    confidence: 0.81,
    sources: [],
    retrieval: {
      queries: ['notice'],
      result_count: 5,
      boosted_count: 2,
      boost_source: 'matter:smith-lease',
    },
  },
  precedents: { precedents: [], summary: '', confidence: 0.8 },
  agent_trace: [],
}

describe('MatterResearch', () => {
  it('scopes the run to the matter and names the ranking boost', async () => {
    let body: Record<string, unknown> | null = null
    server.use(
      http.post('*/api/analysis', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(IRAC_REPLY)
      }),
    )
    render(<MatterResearch matterId={7} jurisdiction="co" />)
    fireEvent.change(screen.getByLabelText(/Question or fact pattern/), {
      target: { value: 'Was the notice good?' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Research' }))
    expect(await screen.findByText(/Service was defective/)).toBeInTheDocument()
    expect(body).toMatchObject({
      text: 'Was the notice good?',
      matter_id: 7,
      jurisdiction: 'co',
    })
    expect(screen.getByTestId('matter-research-boost')).toHaveTextContent(
      /2 passage\(s\) promoted because matter:smith-lease/,
    )
  })

  it('says nothing about ranking when no authority was promoted', async () => {
    server.use(
      http.post('*/api/analysis', () =>
        HttpResponse.json({
          ...IRAC_REPLY,
          irac: {
            ...IRAC_REPLY.irac,
            retrieval: { queries: ['notice'], result_count: 5 },
          },
        }),
      ),
    )
    render(<MatterResearch matterId={7} />)
    fireEvent.change(screen.getByLabelText(/Question or fact pattern/), {
      target: { value: 'Was the notice good?' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Research' }))
    await screen.findByText(/Service was defective/)
    expect(screen.queryByTestId('matter-research-boost')).toBeNull()
  })

  it('reports a refused round without saying whether the matter exists', async () => {
    server.use(
      http.post('*/api/analysis', () =>
        HttpResponse.json({ detail: 'not found' }, { status: 404 }),
      ),
    )
    render(<MatterResearch matterId={7} />)
    fireEvent.change(screen.getByLabelText(/Question or fact pattern/), {
      target: { value: 'Was the notice good?' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Research' }))
    expect(await screen.findByText(/could not be run/)).toBeInTheDocument()
    expect(screen.queryByText(/not found/)).toBeNull()
  })

  it('refuses to run on an empty question', () => {
    render(<MatterResearch matterId={7} />)
    expect(screen.getByRole('button', { name: 'Research' })).toBeDisabled()
  })
})

describe('MatterWorkspace', () => {
  it('offers the matter-scoped research entry point', async () => {
    server.use(
      http.get('*/api/matters/smith-lease', () => HttpResponse.json(MATTER)),
      http.get('*/api/matters/smith-lease/tasks', () =>
        HttpResponse.json({ count: 0, tasks: [] }),
      ),
      http.get('*/api/matters/smith-lease/study-plan', () =>
        HttpResponse.json({
          matter: { slug: 'smith-lease', name: 'Smith', issue_tags: [] },
          covered_tags: [],
          unmapped_tags: [],
          concepts: [],
        }),
      ),
    )
    render(<MatterWorkspace slug="smith-lease" />)
    expect(
      await screen.findByRole('heading', { name: /Research in this matter/i }),
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Research' })).toBeInTheDocument()
  })
})
