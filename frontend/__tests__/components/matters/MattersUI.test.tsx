import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { describe, expect, it, vi } from 'vitest'

import AccountData from '@/components/matters/AccountData'
import MatterList from '@/components/matters/MatterList'
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
