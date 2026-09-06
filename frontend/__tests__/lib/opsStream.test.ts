/**
 * Tests for the ops-dashboard push channel client (BL-20260429-16).
 *
 * The socket is an optimisation over polling, so what matters most is how it
 * fails: no WebSocket, a refused handshake, a mid-session close. Every one of
 * those has to leave the caller polling rather than blind.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import { openOpsStream, opsStreamUrl } from '@/lib/opsStream'

type Handler = ((e: { data: string }) => void) | null

class MockSocket {
  static last: MockSocket | null = null
  static built = 0
  onmessage: Handler = null
  onerror: (() => void) | null = null
  onclose: (() => void) | null = null
  close = vi.fn()
  constructor(public url: string) {
    MockSocket.last = this
    MockSocket.built += 1
  }
}

function stubSocket(): typeof MockSocket {
  MockSocket.last = null
  MockSocket.built = 0
  vi.stubGlobal('WebSocket', MockSocket as unknown as typeof WebSocket)
  return MockSocket
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe('opsStreamUrl', () => {
  it('points at the single ops route, not a per-run stream', () => {
    expect(opsStreamUrl()).toMatch(/^ws:\/\//)
    expect(opsStreamUrl()).toContain('/ws/agents/ops')
  })

  it('carries a ticket, never a key (BL-20260430-07)', () => {
    const url = opsStreamUrl('1700000000.deadbeef')
    expect(url).toContain('ticket=1700000000.deadbeef')
    expect(url).not.toContain('api_key')
  })
})

describe('openOpsStream', () => {
  it('reports live only after the server confirms the subscription', async () => {
    const Sock = stubSocket()
    const status: boolean[] = []
    const changes: string[] = []

    const handle = openOpsStream((e) => changes.push(e.type), {
      onStatus: (live) => status.push(live),
    })
    await vi.waitFor(() => expect(Sock.last).not.toBeNull())

    expect(status).toEqual([])
    Sock.last!.onmessage!({
      data: JSON.stringify({ type: 'ready', channel: 'ops-dashboard' }),
    })
    expect(status).toEqual([true])
    // `ready` is a handshake, not a change: it must not trigger a refetch.
    expect(changes).toEqual([])

    Sock.last!.onmessage!({ data: JSON.stringify({ type: 'runs_changed' }) })
    expect(changes).toEqual(['runs_changed'])
    handle.close()
  })

  it('ignores non-JSON frames rather than tearing down the stream', async () => {
    const Sock = stubSocket()
    const changes: string[] = []

    const handle = openOpsStream((e) => changes.push(e.type))
    await vi.waitFor(() => expect(Sock.last).not.toBeNull())
    Sock.last!.onmessage!({ data: 'not json at all' })
    Sock.last!.onmessage!({ data: JSON.stringify({ type: 'runs_changed' }) })

    expect(changes).toEqual(['runs_changed'])
    handle.close()
  })

  it('reports not-live on close and reconnects with backoff', async () => {
    vi.useFakeTimers()
    const Sock = stubSocket()
    const status: boolean[] = []

    const handle = openOpsStream(() => {}, { onStatus: (l) => status.push(l) })
    await vi.waitUntil(() => Sock.last !== null)
    Sock.last!.onclose!()

    expect(status.at(-1)).toBe(false)
    expect(Sock.built).toBe(1)
    // Backoff, not a reconnect storm: nothing happens before the first second.
    await vi.advanceTimersByTimeAsync(500)
    expect(Sock.built).toBe(1)
    await vi.advanceTimersByTimeAsync(600)
    expect(Sock.built).toBe(2)
    handle.close()
  })

  it('stops reconnecting once closed by the caller', async () => {
    vi.useFakeTimers()
    const Sock = stubSocket()

    const handle = openOpsStream(() => {})
    await vi.waitUntil(() => Sock.last !== null)
    handle.close()
    Sock.last!.onclose!()

    await vi.advanceTimersByTimeAsync(60_000)
    expect(Sock.built).toBe(1)
  })

  it('degrades quietly where there is no WebSocket at all', async () => {
    vi.stubGlobal('WebSocket', undefined)
    const status: boolean[] = []

    const handle = openOpsStream(() => {}, { onStatus: (l) => status.push(l) })
    await vi.waitFor(() => expect(status).toEqual([false]))
    // The caller keeps its polling interval — the pre-push behaviour.
    expect(() => handle.close()).not.toThrow()
  })
})
