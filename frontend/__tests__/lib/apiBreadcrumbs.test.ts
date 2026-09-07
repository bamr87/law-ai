/**
 * Failed API calls have to reach the feedback report.
 *
 * A user reporting "the analysis page is broken" cannot tell you the request
 * returned 502 — the UI shows them a toast, not a status code. `apiFetch`
 * therefore drops a line into the widget's capture buffer on failure, so the
 * issue arrives with the evidence rather than a request for it.
 *
 * Success is deliberately NOT recorded: the buffer is a 40-entry ring, and a
 * ring full of 200s has no room for the one line that explains the failure.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'

import { apiFetch } from '@/lib/api'
import { server } from '@/mocks/server'

const BASE = 'http://localhost:8000'

function captureBuffer() {
  const breadcrumb = vi.fn()
  ;(window as unknown as Record<string, unknown>).__fleetFeedback = { breadcrumb }
  return breadcrumb
}

describe('apiFetch breadcrumbs', () => {
  let breadcrumb: ReturnType<typeof captureBuffer>

  beforeEach(() => {
    breadcrumb = captureBuffer()
  })

  afterEach(() => {
    delete (window as unknown as Record<string, unknown>).__fleetFeedback
  })

  it('records the method, path and status of a failed request', async () => {
    server.use(
      http.post(`${BASE}/api/analysis`, () =>
        HttpResponse.json({ detail: 'upstream down' }, { status: 502 }),
      ),
    )

    const res = await apiFetch('/api/analysis', { method: 'POST' })

    expect(res.status).toBe(502)
    expect(breadcrumb).toHaveBeenCalledTimes(1)
    const [level, message] = breadcrumb.mock.calls[0]
    expect(level).toBe('net')
    expect(message).toContain('POST /api/analysis')
    expect(message).toContain('502')
    // Duration matters: "slow then failed" and "failed instantly" are
    // different bugs, and the reporter cannot tell you which they saw.
    expect(message).toMatch(/\(\d+ms\)/)
  })

  it('records a network error and still rejects', async () => {
    server.use(http.get(`${BASE}/api/graph/x`, () => HttpResponse.error()))

    await expect(apiFetch('/api/graph/x')).rejects.toThrow()

    expect(breadcrumb).toHaveBeenCalledTimes(1)
    expect(breadcrumb.mock.calls[0][1]).toContain('GET /api/graph/x')
    expect(breadcrumb.mock.calls[0][1]).toContain('network error')
  })

  it('stays quiet on success', async () => {
    server.use(http.get(`${BASE}/api/ok`, () => HttpResponse.json({ ok: true })))

    await apiFetch('/api/ok')

    expect(breadcrumb).not.toHaveBeenCalled()
  })

  it('never records headers or bodies — the API key must not reach a report', async () => {
    server.use(
      http.post(`${BASE}/api/analysis`, () =>
        HttpResponse.json({ detail: 'nope' }, { status: 401 }),
      ),
    )

    await apiFetch('/api/analysis', {
      method: 'POST',
      headers: { 'X-API-Key': 'super-secret-key' },
      body: JSON.stringify({ text: 'privileged client matter' }),
    })

    const message = breadcrumb.mock.calls[0][1]
    expect(message).not.toContain('super-secret-key')
    expect(message).not.toContain('privileged client matter')
  })
})
