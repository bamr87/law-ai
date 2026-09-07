import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AccountMenu from '@/components/shell/AccountMenu'
import { server } from '@/mocks/server'

/**
 * The sign-in surface (BL-20260906-08).
 *
 * `/api/auth/login` shipped with spec 036 and nothing rendered a form for it,
 * so a session could only be had by logging into Django's `/admin/`. These
 * pin the three things that closes: a way in, a way out, and a refusal that
 * neither strands the user nor tells them which half was wrong.
 */
vi.mock('@/lib/shell/reload', () => ({ reloadPage: vi.fn() }))

const signedIn = {
  authenticated: true,
  username: 'dana',
  id: 7,
  is_staff: false,
  scopes: [],
}

function whoami(body: Record<string, unknown>) {
  server.use(http.get('*/api/auth/me', () => HttpResponse.json(body)))
}

function open() {
  fireEvent.click(screen.getByRole('button', { name: /Sign in|dana/ }))
  return screen.getByRole('dialog', { name: 'Account' })
}

/** The form's own submit, not the masthead trigger that shares its label. */
function submit() {
  const panel = screen.getByRole('dialog', { name: 'Account' })
  fireEvent.click(within(panel).getByRole('button', { name: 'Sign in' }))
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('AccountMenu', () => {
  it('offers a sign-in form to an anonymous visitor', async () => {
    render(<AccountMenu />)
    const button = await screen.findByRole('button', { name: 'Sign in' })
    expect(button).toHaveAttribute('aria-expanded', 'false')
    open()
    expect(screen.getByLabelText('Username')).toBeInTheDocument()
    expect(screen.getByLabelText('Password')).toBeInTheDocument()
  })

  it('signs in through /api/auth/{csrf,login} and reloads', async () => {
    const { reloadPage } = await import('@/lib/shell/reload')
    let sentCsrf: string | null = null
    let sentBody: unknown = null
    server.use(
      http.post('*/api/auth/login', async ({ request }) => {
        sentCsrf = request.headers.get('X-CSRFToken')
        sentBody = await request.json()
        return HttpResponse.json(signedIn)
      }),
    )

    render(<AccountMenu />)
    await screen.findByRole('button', { name: 'Sign in' })
    open()
    fireEvent.change(screen.getByLabelText('Username'), {
      target: { value: 'dana' },
    })
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: 'hunter2' },
    })
    submit()

    // The button becomes the identity: the whole point is that a signed-in
    // user can see they are, without opening Django's admin to find out.
    await screen.findByRole('button', { name: 'dana' })
    // Double-submit CSRF: the token from `GET csrf` rides in the header.
    expect(sentCsrf).toBe('test-csrf-token')
    expect(sentBody).toEqual({ username: 'dana', password: 'hunter2' })
    expect(reloadPage).toHaveBeenCalled()
  })

  it('keeps the form up and says so when the credentials are refused', async () => {
    // The mock default is a 401 with the backend's own wording.
    render(<AccountMenu />)
    await screen.findByRole('button', { name: 'Sign in' })
    open()
    fireEvent.change(screen.getByLabelText('Username'), {
      target: { value: 'dana' },
    })
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: 'wrong' },
    })
    submit()

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('invalid credentials')
    // Still anonymous, still on the form — nothing to re-find.
    expect(screen.getByLabelText('Password')).toBeInTheDocument()
  })

  it('shows who is signed in and signs them back out', async () => {
    const { reloadPage } = await import('@/lib/shell/reload')
    whoami(signedIn)
    let loggedOut = false
    server.use(
      http.post('*/api/auth/logout', () => {
        loggedOut = true
        return HttpResponse.json({ authenticated: false })
      }),
    )

    render(<AccountMenu />)
    fireEvent.click(await screen.findByRole('button', { name: 'dana' }))
    const panel = screen.getByRole('dialog', { name: 'Account' })
    expect(panel).toHaveTextContent('Signed in as dana')

    fireEvent.click(screen.getByRole('button', { name: 'Sign out' }))
    await waitFor(() => expect(loggedOut).toBe(true))
    expect(reloadPage).toHaveBeenCalled()
  })

  it('renders nothing at all while the identity probe is in flight', () => {
    server.use(
      http.get('*/api/auth/me', () => new Promise(() => {})),
    )
    const { container } = render(<AccountMenu />)
    // No flicker of "Sign in" under a visitor who turns out to be signed in.
    expect(container).toBeEmptyDOMElement()
  })

  it('closes on Escape and hands focus back to its button', async () => {
    render(<AccountMenu />)
    const button = await screen.findByRole('button', { name: 'Sign in' })
    open()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(document.activeElement).toBe(button)
  })
})
