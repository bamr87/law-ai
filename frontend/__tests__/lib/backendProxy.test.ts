import { createHmac } from 'crypto'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { GET as proxyGet, POST as proxyPost } from '@/app/api/backend/[...path]/route'
import { GET as ticketGet } from '@/app/api/ws-ticket/route'

/**
 * The server side of "no key in the browser" (BL-20260430-07).
 *
 * These two route handlers are the only places the shared key is read, so
 * they are the only places a leak can come back: the proxy must attach the
 * key the browser cannot have, refuse to let a client set that header itself,
 * and pass everything else through untouched.
 */
function params(path: string[]) {
  return { params: Promise.resolve({ path }) }
}

afterEach(() => {
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
})

function stubUpstream(
  impl: (url: string, init: RequestInit) => Response | Promise<Response>,
) {
  const spy = vi.fn(impl)
  vi.stubGlobal('fetch', spy as unknown as typeof fetch)
  return spy
}

describe('backend proxy route', () => {
  it('forwards path, query and method to the internal backend', async () => {
    vi.stubEnv('BACKEND_INTERNAL_URL', 'http://backend:8000')
    const upstream = stubUpstream(() =>
      Response.json({ count: 0 }, { status: 200 }),
    )

    const res = await proxyGet(
      new Request('http://app.test/api/backend/api/agents/runs?limit=25'),
      params(['api', 'agents', 'runs']),
    )

    expect(upstream).toHaveBeenCalledTimes(1)
    expect(upstream.mock.calls[0][0]).toBe(
      'http://backend:8000/api/agents/runs?limit=25',
    )
    expect(res.status).toBe(200)
    await expect(res.json()).resolves.toEqual({ count: 0 })
  })

  it('attaches the server-only key, and never one the client supplied', async () => {
    vi.stubEnv('AGENT_API_KEY', 's3cret')
    const upstream = stubUpstream(() => Response.json({ ok: true }))

    await proxyGet(
      new Request('http://app.test/api/backend/api/agents', {
        headers: { 'X-API-Key': 'forged', 'X-Trace': 'keep-me' },
      }),
      params(['api', 'agents']),
    )

    const sent = new Headers(upstream.mock.calls[0][1].headers as HeadersInit)
    expect(sent.get('x-api-key')).toBe('s3cret')
    // Ordinary headers ride through; only the credential is the proxy's.
    expect(sent.get('x-trace')).toBe('keep-me')
  })

  /**
   * BL-20260906-08: the session has to survive the hop, in both directions.
   *
   * With `cookie` stripped, no browser session could ever reach Django through
   * this proxy — the Share control and the matters screens worked only for
   * someone who had logged into `/admin/` and was talking to the backend's
   * origin directly.
   */
  it('carries the session cookie upstream and Set-Cookie back', async () => {
    const upstream = stubUpstream(
      () =>
        new Response(JSON.stringify({ authenticated: true }), {
          status: 200,
          headers: [
            ['content-type', 'application/json'],
            ['set-cookie', 'sessionid=abc; Path=/; HttpOnly'],
            ['set-cookie', 'csrftoken=xyz; Path=/'],
          ],
        }),
    )

    const res = await proxyPost(
      new Request('http://app.test/api/backend/api/auth/login', {
        method: 'POST',
        headers: {
          cookie: 'csrftoken=xyz',
          'X-CSRFToken': 'xyz',
          'Content-Type': 'application/json',
        },
        body: '{}',
      }),
      params(['api', 'auth', 'login']),
    )

    const sent = new Headers(upstream.mock.calls[0][1].headers as HeadersInit)
    expect(sent.get('cookie')).toBe('csrftoken=xyz')
    expect(sent.get('x-csrftoken')).toBe('xyz')
    // Both cookies come back as separate headers: folded into one, a browser
    // keeps the first and drops the session.
    expect(res.headers.getSetCookie()).toEqual([
      'sessionid=abc; Path=/; HttpOnly',
      'csrftoken=xyz; Path=/',
    ])
  })

  it('does not forward the browser origin, which Django would reject', async () => {
    // This hop is a server-side fetch, not a cross-origin browser request:
    // `http://app.test` is never going to match the backend's own host, and
    // DRF's session CSRF check verifies `Origin` when one is present.
    const upstream = stubUpstream(() => Response.json({ ok: true }))
    await proxyPost(
      new Request('http://app.test/api/backend/api/auth/login', {
        method: 'POST',
        headers: { origin: 'http://app.test', referer: 'http://app.test/x' },
        body: '{}',
      }),
      params(['api', 'auth', 'login']),
    )
    const sent = new Headers(upstream.mock.calls[0][1].headers as HeadersInit)
    expect(sent.get('origin')).toBeNull()
    expect(sent.get('referer')).toBeNull()
  })

  it('sends no key at all when none is configured', async () => {
    const upstream = stubUpstream(() => Response.json({ ok: true }))
    await proxyGet(
      new Request('http://app.test/api/backend/api/graph/stats'),
      params(['api', 'graph', 'stats']),
    )
    const sent = new Headers(upstream.mock.calls[0][1].headers as HeadersInit)
    expect(sent.get('x-api-key')).toBeNull()
  })

  it('passes a POST body through and returns the upstream status', async () => {
    const upstream = stubUpstream(async (_url, init) => {
      const body = new TextDecoder().decode(init.body as ArrayBuffer)
      expect(JSON.parse(body)).toEqual({ query: 'hi' })
      return Response.json({ detail: 'nope' }, { status: 422 })
    })

    const res = await proxyPost(
      new Request('http://app.test/api/backend/api/analysis', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: 'hi' }),
      }),
      params(['api', 'analysis']),
    )

    expect(upstream).toHaveBeenCalledTimes(1)
    expect(res.status).toBe(422)
    await expect(res.json()).resolves.toEqual({ detail: 'nope' })
  })

  it('answers 502 rather than throwing when the backend is down', async () => {
    stubUpstream(() => {
      throw new Error('ECONNREFUSED')
    })
    const res = await proxyGet(
      new Request('http://app.test/api/backend/api/agents'),
      params(['api', 'agents']),
    )
    expect(res.status).toBe(502)
  })
})

describe('ws-ticket route', () => {
  it('refuses a stream id the consumer would reject', async () => {
    const res = await ticketGet(
      new Request('http://app.test/api/ws-ticket?stream=not%20valid'),
    )
    expect(res.status).toBe(400)
  })

  it('hands back no ticket when no key is configured', async () => {
    const res = await ticketGet(
      new Request('http://app.test/api/ws-ticket?stream=run-abc'),
    )
    await expect(res.json()).resolves.toEqual({ ticket: null })
  })

  it('signs the stream id and an expiry with the server-only key', async () => {
    vi.stubEnv('AGENT_API_KEY', 's3cret')
    const res = await ticketGet(
      new Request('http://app.test/api/ws-ticket?stream=run-abc'),
    )
    const body = (await res.json()) as { ticket: string; expiresAt: number }
    const [expiry, mac] = body.ticket.split('.')

    // The format `law_ai/core/ws_ticket.py` verifies, byte for byte.
    expect(mac).toBe(
      createHmac('sha256', 's3cret').update(`run-abc.${expiry}`).digest('hex'),
    )
    expect(Number(expiry)).toBe(body.expiresAt)
    expect(Number(expiry)).toBeGreaterThan(Date.now() / 1000)
    // Short-lived: a leaked ticket is worthless within the minute.
    expect(Number(expiry)).toBeLessThanOrEqual(Date.now() / 1000 + 60)
    // A ticket for one stream must not sign another.
    expect(mac).not.toBe(
      createHmac('sha256', 's3cret').update(`run-other.${expiry}`).digest('hex'),
    )
    expect(res.headers.get('cache-control')).toContain('no-store')
  })
})
