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
  onmessage: Handler = null
  onerror: (() => void) | null = null
  close = vi.fn()
  constructor(public url: string) {
    MockSocket.last = this
  }
}

function stubSocket(): typeof MockSocket {
  MockSocket.last = null
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
})

describe('openAgentStream', () => {
  it('resolves only once the server confirms the subscription', async () => {
    const Sock = stubSocket()
    const seen: { type: string }[] = []

    const pending = openAgentStream('run-xyz', (e) => seen.push(e))
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
    Sock.last!.onerror!()
    await expect(pending).rejects.toThrow(/connection failed/)
  })
})
