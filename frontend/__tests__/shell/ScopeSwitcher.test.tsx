import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import ScopeSwitcher from '@/components/shell/ScopeSwitcher'
import { getActiveScope, resetActiveScope } from '@/lib/scope/active'
import { server } from '@/mocks/server'

/**
 * BL-20260830-08. The item names its own trap: a scope switcher that trusts a
 * URL is an IDOR vector. So the assertions are about *where the id comes
 * from*, not just about what renders.
 */

let searchParams = new URLSearchParams()

vi.mock('next/navigation', () => ({
  useSearchParams: () => searchParams,
}))

const MATTERS = {
  count: 2,
  matters: [
    {
      id: 7,
      slug: 'smith-lease',
      name: 'Smith lease dispute',
      stage: 'research',
      issue_tags: ['landlord-tenant'],
      jurisdiction: 'co',
      updated_at: '2026-09-01T00:00:00Z',
    },
    {
      id: 9,
      slug: 'acme-merger',
      name: 'Acme merger',
      stage: 'intake',
      issue_tags: [],
      jurisdiction: '',
      updated_at: '2026-09-02T00:00:00Z',
    },
  ],
}

function mockMatters(body: unknown = MATTERS, status = 200) {
  server.use(
    http.get('*/api/matters', () => HttpResponse.json(body, { status })),
  )
}

/**
 * The identity probe the switcher runs before anything account-scoped
 * (BL-20260906-68). The MSW default is "signed out", so every test that
 * expects matters to be fetched has to say who it is first.
 */
function mockSignedIn(authenticated = true) {
  server.use(
    http.get('*/api/auth/me', () =>
      HttpResponse.json({
        authenticated,
        username: authenticated ? 'ada' : null,
        id: authenticated ? 7 : null,
        is_staff: false,
        scopes: [],
      }),
    ),
  )
}

/** Records every `/api/matters*` request MSW sees, in order. */
function watchMatterRequests(): string[] {
  const seen: string[] = []
  server.events.on('request:start', ({ request }) => {
    const path = new URL(request.url).pathname
    if (path.startsWith('/api/matters')) seen.push(path)
  })
  return seen
}

beforeEach(() => {
  searchParams = new URLSearchParams()
  resetActiveScope()
})

afterEach(() => {
  resetActiveScope()
  // watchMatterRequests() attaches a listener per test; MSW does not clear
  // those with resetHandlers().
  server.events.removeAllListeners()
})

describe('ScopeSwitcher', () => {
  it('falls back to the instance readout when the caller owns no matters', async () => {
    mockSignedIn()
    mockMatters({ count: 0, matters: [] })
    render(<ScopeSwitcher />)
    await waitFor(() =>
      expect(screen.getByText(/Law AI \(local\)/)).toBeInTheDocument(),
    )
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  })

  it('stays on the instance readout when the caller is signed out', async () => {
    mockMatters({ detail: 'sign in' }, 401)
    render(<ScopeSwitcher />)
    await waitFor(() =>
      expect(screen.getByText(/Law AI \(local\)/)).toBeInTheDocument(),
    )
  })

  it('asks for nothing account-scoped while signed out', async () => {
    // BL-20260906-68: the shell renders on every page, so a speculative
    // `/api/matters` meant a 401 per anonymous page view.
    searchParams = new URLSearchParams('matter=smith-lease')
    const seen = watchMatterRequests()
    mockMatters({ detail: 'sign in' }, 401)
    render(<ScopeSwitcher />)
    await waitFor(() =>
      expect(screen.getByText(/Law AI \(local\)/)).toBeInTheDocument(),
    )
    expect(seen).toEqual([])
  })

  it('asks once it knows it is signed in', async () => {
    const seen = watchMatterRequests()
    mockSignedIn()
    mockMatters()
    render(<ScopeSwitcher />)
    await screen.findByRole('combobox', { name: 'Active scope' })
    expect(seen).toContain('/api/matters')
  })

  it('lists the caller’s own matters', async () => {
    mockSignedIn()
    mockMatters()
    render(<ScopeSwitcher />)
    const select = await screen.findByRole('combobox', { name: 'Active scope' })
    expect(select).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Smith lease dispute' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Acme merger' })).toBeInTheDocument()
  })

  it('builds the scope id from the server row, not from the slug', async () => {
    mockSignedIn()
    mockMatters()
    render(<ScopeSwitcher />)
    const select = await screen.findByRole('combobox', { name: 'Active scope' })
    fireEvent.change(select, { target: { value: 'smith-lease' } })
    await waitFor(() => expect(getActiveScope()?.id).toBe('project:7'))
    expect(getActiveScope()?.type).toBe('project')
    expect(getActiveScope()?.parentId).toBe('instance:local')
  })

  it('resolves a URL slug through the server and takes the id from the response', async () => {
    searchParams = new URLSearchParams('matter=smith-lease')
    mockSignedIn()
    mockMatters()
    server.use(
      http.get('*/api/matters/smith-lease', () =>
        HttpResponse.json({ ...MATTERS.matters[0], id: 42 }),
      ),
    )
    render(<ScopeSwitcher />)
    // 42 comes from the fetch; the URL never said it.
    await waitFor(() => expect(getActiveScope()?.id).toBe('project:42'))
  })

  it('an unowned or unknown slug leaves the shell on the instance scope', async () => {
    searchParams = new URLSearchParams('matter=someone-elses')
    mockSignedIn()
    mockMatters()
    server.use(
      http.get('*/api/matters/someone-elses', () =>
        HttpResponse.json({ detail: 'matter not found' }, { status: 404 }),
      ),
    )
    render(<ScopeSwitcher />)
    await screen.findByRole('combobox', { name: 'Active scope' })
    await waitFor(() => expect(getActiveScope()).toBeNull())
    // No error surfaced: "not yours" must look like "does not exist".
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('clearing the selection returns to the instance scope', async () => {
    mockSignedIn()
    mockMatters()
    render(<ScopeSwitcher />)
    const select = await screen.findByRole('combobox', { name: 'Active scope' })
    fireEvent.change(select, { target: { value: 'acme-merger' } })
    await waitFor(() => expect(getActiveScope()?.id).toBe('project:9'))
    fireEvent.change(select, { target: { value: '' } })
    await waitFor(() => expect(getActiveScope()).toBeNull())
  })
})
