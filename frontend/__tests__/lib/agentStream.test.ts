/**
 * Tests for the live agent-run stream client (spec 032 / BL-20260810-06).
 */
import { describe, it, expect, vi, afterEach } from 'vitest'

import {
  agentStreamUrl,
  newStreamId,
  openAgentStream,
} from '@/lib/agentStream'

type Handler = ((e: { data: string }) => void) | null

class MockSocket {
  static last: MockSocket | null = null
  static urls: string[] = []
  onmessage: Handler = null
  onerror: (() => void) | null = null
  onclose: (() => void) | null = null
  close = vi.fn()
  constructor(public url: string) {
    MockSocket.last = this
    MockSocket.urls.push(url)
  }
}

function stubSocket(): typeof MockSocket {
  MockSocket.last = null
  MockSocket.urls = []
  vi.stubGlobal('WebSocket', MockSocket as unknown as typeof WebSocket)
  return MockSocket
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('newStreamId', () => {
  it('always satisfies the server contract ^[A-Za-z0-9._-]{1,64}$', () => {
    for (let i = 0; i < 20; i++) {
      expect(newStreamId()).toMatch(/^[A-Za-z0-9._-]{1,64}$/)
    }
  })

  it('produces distinct ids', () => {
    const ids = new Set(Array.from({ length: 10 }, () => newStreamId()))
    expect(ids.size).toBe(10)
  })
})

describe('agentStreamUrl', () => {
  it('converts the http api base to a ws url on the consumer route', () => {
    const url = agentStreamUrl('run-abc')
    expect(url).toMatch(/^ws:\/\//)
    expect(url).toContain('/ws/agents/run-abc')
  })

  it('carries a ticket, never a key (BL-20260430-07)', () => {
    const url = agentStreamUrl('run-abc', '1700000000.deadbeef')
    expect(url).toContain('ticket=1700000000.deadbeef')
    expect(url).not.toContain('api_key')
  })

  it('connects unauthenticated when no ticket is needed', () => {
    expect(agentStreamUrl('run-abc', null)).not.toContain('?')
  })
})

describe('openAgentStream', () => {
  it('resolves only once the server confirms the subscription', async () => {
    const Sock = stubSocket()
    const seen: { type: string }[] = []

    const pending = openAgentStream('run-xyz', (e) => seen.push(e))
    // The socket opens after one round trip to the ticket route, so let that
    // settle before driving frames through it (BL-20260430-07).
    await vi.waitFor(() => expect(Sock.last).not.toBeNull())
    // A step frame alone must NOT resolve: resolving before `ready` would
    // reintroduce the subscribe-after-post race this design removes.
    Sock.last!.onmessage!({
      data: JSON.stringify({ type: 'agent_step', agent: 'LegalAnalyst' }),
    })
    Sock.last!.onmessage!({
      data: JSON.stringify({ type: 'ready', run_id: 'run-xyz' }),
    })

    await expect(pending).resolves.toBeDefined()
    expect(seen.map((e) => e.type)).toEqual(['agent_step', 'ready'])
  })

  it('ignores non-JSON frames rather than tearing down the stream', async () => {
    const Sock = stubSocket()
    const seen: { type: string }[] = []

    const pending = openAgentStream('run-junk', (e) => seen.push(e))
    await vi.waitFor(() => expect(Sock.last).not.toBeNull())
    Sock.last!.onmessage!({ data: 'not json at all' })
    Sock.last!.onmessage!({
      data: JSON.stringify({ type: 'ready', run_id: 'run-junk' }),
    })

    await expect(pending).resolves.toBeDefined()
    expect(seen).toHaveLength(1)
  })

  it('rejects on connection error', async () => {
    const Sock = stubSocket()
    const pending = openAgentStream('run-bad', () => {})
    await vi.waitFor(() => expect(Sock.last).not.toBeNull())
    Sock.last!.onerror!()
    await expect(pending).rejects.toThrow(/connection failed/)
  })
})

// --- BL-20260811-14: a dropped socket must not lose the in-flight trace ---

describe('openAgentStream reconnect + replay', () => {
  it('reconnects with the last seq it saw', async () => {
    vi.useFakeTimers()
    const Sock = stubSocket()
    const seen: { type: string }[] = []

    const pending = openAgentStream('run-drop', (e) => seen.push(e), {
      reconnectBaseMs: 10,
    })
    await vi.waitUntil(() => Sock.last !== null)
    Sock.last!.onmessage!({
      data: JSON.stringify({ type: 'ready', run_id: 'run-drop', since: 0 }),
    })
    await pending
    Sock.last!.onmessage!({
      data: JSON.stringify({ type: 'agent_step', agent: 'A', seq: 1 }),
    })

    Sock.last!.onclose!()
    await vi.advanceTimersByTimeAsync(50)

    expect(Sock.urls).toHaveLength(2)
    expect(Sock.urls[1]).toContain('since=1')
    expect(Sock.urls[1]).toContain('replay=1')
    vi.useRealTimers()
  })

  it('drops replayed events the consumer already saw', async () => {
    vi.useFakeTimers()
    const Sock = stubSocket()
    const seen: { type: string; agent?: string }[] = []

    const pending = openAgentStream('run-dupe', (e) => seen.push(e), {
      reconnectBaseMs: 10,
    })
    await vi.waitUntil(() => Sock.last !== null)
    Sock.last!.onmessage!({
      data: JSON.stringify({ type: 'ready', run_id: 'run-dupe' }),
    })
    await pending
    Sock.last!.onmessage!({
      data: JSON.stringify({ type: 'agent_step', agent: 'A', seq: 1 }),
    })
    Sock.last!.onclose!()
    await vi.advanceTimersByTimeAsync(50)

    // The replay window overlaps by design; the client, not the caller, dedupes.
    Sock.last!.onmessage!({
      data: JSON.stringify({ type: 'agent_step', agent: 'A', seq: 1 }),
    })
    Sock.last!.onmessage!({
      data: JSON.stringify({ type: 'agent_step', agent: 'B', seq: 2 }),
    })

    expect(seen.filter((e) => e.type === 'agent_step').map((e) => e.agent)).toEqual([
      'A',
      'B',
    ])
    vi.useRealTimers()
  })

  it('stops reconnecting once the run completes', async () => {
    vi.useFakeTimers()
    const Sock = stubSocket()

    const pending = openAgentStream('run-done', () => {}, { reconnectBaseMs: 10 })
    await vi.waitUntil(() => Sock.last !== null)
    Sock.last!.onmessage!({
      data: JSON.stringify({ type: 'ready', run_id: 'run-done' }),
    })
    await pending
    Sock.last!.onmessage!({
      data: JSON.stringify({ type: 'complete', analysis_id: 'an-1', seq: 1 }),
    })
    Sock.last!.onclose!()
    await vi.advanceTimersByTimeAsync(1000)

    expect(Sock.urls).toHaveLength(1)
    vi.useRealTimers()
  })

  it('stops reconnecting once the caller closes the stream', async () => {
    vi.useFakeTimers()
    const Sock = stubSocket()

    const pending = openAgentStream('run-closed', () => {}, {
      reconnectBaseMs: 10,
    })
    await vi.waitUntil(() => Sock.last !== null)
    Sock.last!.onmessage!({
      data: JSON.stringify({ type: 'ready', run_id: 'run-closed' }),
    })
    const socket = await pending
    socket.close()
    Sock.last!.onclose!()
    await vi.advanceTimersByTimeAsync(1000)

    expect(Sock.urls).toHaveLength(1)
    vi.useRealTimers()
  })

  it('gives up after a bounded number of attempts', async () => {
    vi.useFakeTimers()
    const Sock = stubSocket()

    const pending = openAgentStream('run-flaky', () => {}, {
      reconnectBaseMs: 10,
      maxReconnects: 2,
    })
    await vi.waitUntil(() => Sock.last !== null)
    Sock.last!.onmessage!({
      data: JSON.stringify({ type: 'ready', run_id: 'run-flaky' }),
    })
    await pending

    // Every reconnect drops again without ever handshaking, so the backoff is
    // never reset — an overnight tab must not become a reconnect storm.
    for (let i = 0; i < 5; i++) {
      Sock.last!.onclose!()
      await vi.advanceTimersByTimeAsync(1000)
    }

    expect(Sock.urls).toHaveLength(3) // the original plus two retries
    vi.useRealTimers()
  })
})
