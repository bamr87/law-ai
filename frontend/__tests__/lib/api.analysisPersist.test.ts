/** Revisiting a persisted analysis by id (BL-20260429-25). */
import { describe, expect, it } from 'vitest'

import { fetchAnalysis } from '@/lib/api'
import { server } from '@/mocks/server'
import { http, HttpResponse } from 'msw'

const persisted = {
  id: 'an-abc123',
  timestamp: '2026-09-05T12:00:00Z',
  latency_ms: 1200,
  confidence: 0.85,
  requires_human_review: false,
  irac: {
    issue: 'Was the contract breached?',
    rule: 'A promise unperformed is a breach.',
    application: 'It was not performed.',
    conclusion: 'Breach.',
    sources: [],
    confidence: 0.85,
  },
  precedents: { precedents: [], summary: '', confidence: 0.8 },
  agent_trace: [],
  persisted: true,
  created_at: '2026-09-05T12:00:00Z',
  trace_id: 'trace-parent',
  child_trace_ids: ['trace-analyst', 'trace-hunter'],
  request: { text: 'Did the seller breach?' },
}

describe('fetchAnalysis', () => {
  it('returns the persisted run with its trace ids', async () => {
    server.use(
      http.get('http://localhost:8000/api/analysis/an-abc123', () =>
        HttpResponse.json(persisted),
      ),
    )
    const run = await fetchAnalysis('an-abc123')
    expect(run?.id).toBe('an-abc123')
    expect(run?.child_trace_ids).toEqual(['trace-analyst', 'trace-hunter'])
    expect(run?.request.text).toBe('Did the seller breach?')
  })

  it('resolves to null for an unknown or archived id', async () => {
    server.use(
      http.get('http://localhost:8000/api/analysis/an-gone', () =>
        HttpResponse.json({ detail: 'analysis an-gone not found' }, { status: 404 }),
      ),
    )
    await expect(fetchAnalysis('an-gone')).resolves.toBeNull()
  })

  it('throws on a server error rather than pretending the run is missing', async () => {
    server.use(
      http.get('http://localhost:8000/api/analysis/an-boom', () =>
        HttpResponse.text('boom', { status: 500 }),
      ),
    )
    await expect(fetchAnalysis('an-boom')).rejects.toThrow(/500/)
  })

  it('escapes the id so a hostile permalink cannot rewrite the path', async () => {
    const seen: string[] = []
    server.use(
      http.get('http://localhost:8000/api/analysis/*', ({ request }) => {
        seen.push(request.url)
        return HttpResponse.json(persisted)
      }),
    )
    await fetchAnalysis('../agents/runs')
    expect(seen[0]).toContain('%2F')
  })
})
