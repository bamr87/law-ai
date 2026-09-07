import { expect, test } from '@playwright/test'

import { apiHeaders, apiQuery } from './apiKey'

/**
 * The boundary jsdom cannot cross (spec 051 / BL-20260811-16).
 *
 * `__tests__/lib/agentStream.test.ts` stubs `WebSocket` with a fake class,
 * because jsdom has none — so the unit suite only ever exercises the fallback
 * path, and nothing proved that a real browser talking to real Channels over
 * real Redis gets `ready → agent_step → complete` in that order. This spec is
 * that proof, and it is the reason the harness exists.
 *
 * It runs against `backend-e2e`, whose provider chain is pinned to an Ollama
 * that is deliberately unreachable: every run takes the degraded path, so the
 * event sequence is deterministic and no third-party model is billed.
 */

type StreamEvent = { type: string; [k: string]: unknown }

/**
 * Do what `lib/agentStream.ts` does — subscribe, wait for `ready`, and only
 * then POST — from inside the page, so the browser's own WebSocket and fetch
 * stacks are the ones under test.
 */
async function runStreamedAnalysis(
  page: import('@playwright/test').Page,
  text: string,
): Promise<StreamEvent[]> {
  return page.evaluate(async ({ factPattern, query, headers }) => {
    const streamId = `e2e-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`
    const events: StreamEvent[] = []
    const socket = new WebSocket(`ws://localhost:8000/ws/agents/${streamId}${query}`)

    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(
        () => reject(new Error('timed out waiting for `ready`')),
        15_000,
      )
      socket.addEventListener('message', (ev) => {
        const payload = JSON.parse(ev.data as string)
        events.push(payload)
        if (payload.type === 'ready') {
          clearTimeout(timer)
          resolve()
        }
      })
      socket.addEventListener('error', () => {
        clearTimeout(timer)
        reject(new Error('socket error before `ready`'))
      })
    })

    const res = await fetch('http://localhost:8000/api/analysis', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...headers },
      body: JSON.stringify({
        text: factPattern,
        use_langgraph: true,
        stream_id: streamId,
      }),
    })
    if (!res.ok) throw new Error(`POST /api/analysis -> ${res.status}`)
    const body = await res.json()

    // The REST response is authoritative; give the trailing `complete` event
    // a moment to arrive over the socket before we judge the sequence.
    await new Promise((r) => setTimeout(r, 1_500))
    socket.close()
    events.push({ type: '__rest__', ...body })
    return events
  }, { factPattern: text, query: apiQuery(), headers: apiHeaders() })
}

test('a real WebSocket receives ready → agent_step → complete', async ({
  page,
}) => {
  await page.goto('/analysis')
  const events = await runStreamedAnalysis(
    page,
    'A state statute bans anonymous political leafleting. Is it constitutional?',
  )

  const types = events.filter((e) => e.type !== '__rest__').map((e) => e.type)
  expect(types[0], 'the server confirms the subscription first').toBe('ready')
  expect(types, 'at least one agent reported in').toContain('agent_step')
  expect(types.at(-1), 'the run is terminated by `complete`').toBe('complete')
  // Ordering, not just membership: every step precedes the completion.
  expect(types.lastIndexOf('agent_step')).toBeLessThan(
    types.lastIndexOf('complete'),
  )

  const steps = events.filter((e) => e.type === 'agent_step')
  expect(steps.map((e) => e.agent).sort()).toEqual([
    'LegalAnalyst',
    'PrecedentHunter',
  ])
  for (const step of steps) {
    expect(typeof step.latency_ms, `${step.agent}.latency_ms`).toBe('number')
    expect(typeof step.confidence, `${step.agent}.confidence`).toBe('number')
  }

  // The socket's ids agree with the REST body — the two halves of the
  // boundary describe the same run.
  const rest = events.find((e) => e.type === '__rest__') as Record<
    string,
    unknown
  >
  const complete = events.find((e) => e.type === 'complete')!
  expect(complete.analysis_id).toBe(rest.id)
  expect(complete.requires_human_review).toBe(rest.requires_human_review)
})

test('the browser UI itself opens a real socket and receives the run', async ({
  page,
}) => {
  // Frames are captured at the browser level, not asserted against the
  // transient "Agents reporting" panel: that panel only exists while
  // `submitting` is true, and on the degraded path the window between the
  // first step and the response is a few hundred milliseconds. What matters
  // is that the UI's own socket carried the run — which jsdom can never show.
  const frames: string[] = []
  let socketUrl = ''
  page.on('websocket', (ws) => {
    // Next dev keeps its own HMR socket open on the same origin; only the
    // agent-run stream carries JSON events.
    if (!ws.url().includes('/ws/agents/')) return
    socketUrl = ws.url()
    ws.on('framereceived', (frame) => frames.push(frame.payload as string))
  })

  await page.goto('/analysis')
  await page.waitForLoadState('networkidle')
  // `openAgentStream` gives the server 5s to answer `ready`, retries once, and
  // silently falls back to a non-streamed run if both windows pass
  // (BL-20260905-21). On a cold Channels layer that handshake can still lose
  // the race, so warm it with a throwaway socket first —
  // this test is about the UI's socket carrying the run, not about how slowly
  // Redis wakes up.
  await page.evaluate(async (query) => {
    const warm = new WebSocket(`ws://localhost:8000/ws/agents/warmup${query}`)
    await new Promise((resolve) => {
      warm.addEventListener('message', resolve, { once: true })
      setTimeout(resolve, 5_000)
    })
    warm.close()
  }, apiQuery())

  await page.getByRole('button', { name: 'Load sample' }).click()
  await page.getByRole('button', { name: /run analysis/i }).click()

  // The durable end state: the IRAC card is on screen, so the run finished.
  await expect(page.getByRole('region', { name: /irac brief/i })).toBeVisible({
    timeout: 60_000,
  })

  expect(socketUrl, 'the UI opened an agent-run socket').toContain('/ws/agents/')
  // BL-20260905-26: the handshake carries a short-lived, stream-scoped ticket
  // minted server-side, never the shared key — a browser cannot set headers on
  // a WebSocket, which is how the key used to end up in the query string.
  expect(socketUrl, 'no shared key in the handshake').not.toContain('api_key=')
  if (process.env.E2E_AGENT_API_KEY) {
    expect(socketUrl, 'a gated stack mints a ticket').toContain('ticket=')
  }
  // The trailing `complete` can land a beat after the REST response.
  await expect
    .poll(() => frames.length, { message: 'socket frames', timeout: 10_000 })
    .toBeGreaterThan(2)
  const types = frames.map((f) => JSON.parse(f).type)
  expect(types[0]).toBe('ready')
  expect(types).toContain('agent_step')
  expect(types).toContain('complete')
  expect(
    frames.some((f) => f.includes('LegalAnalyst')),
    'LegalAnalyst reported over the socket',
  ).toBe(true)
})

test('an over-long stream id never joins a group', async ({ page }) => {
  await page.goto('/analysis')
  const outcome = await page.evaluate(async () => {
    // Valid characters (the ASGI route matches [\w-]+) but 80 of them, so the
    // consumer's own ^[A-Za-z0-9._-]{1,64}$ guard is what rejects it.
    const tooLong = 'e'.repeat(80)
    const socket = new WebSocket(`ws://localhost:8000/ws/agents/${tooLong}`)
    const received: string[] = []
    socket.addEventListener('message', (ev) => received.push(ev.data as string))
    return new Promise<{ closed: boolean; clean: boolean; received: string[] }>(
      (resolve) => {
        socket.addEventListener('close', (ev) =>
          resolve({ closed: true, clean: ev.wasClean, received }),
        )
        setTimeout(
          () => resolve({ closed: false, clean: false, received }),
          10_000,
        )
      },
    )
  })

  // The consumer closes before `accept()`, so the handshake itself is refused
  // and the browser reports an abnormal close rather than the app's 4400 —
  // what matters is that no group was joined and not one event was delivered.
  expect(outcome.closed, 'the server hung up').toBe(true)
  expect(outcome.clean).toBe(false)
  expect(outcome.received, 'not even `ready` is sent').toEqual([])
})
