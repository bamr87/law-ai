import { activityFeedUrl, useAgentActivity } from '@/lib/useAgentActivity'
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// ---------------------------------------------------------------------------
// Controllable WebSocket double — lets the test drive open/message/close.
// ---------------------------------------------------------------------------
class MockWebSocket {
  static instances: MockWebSocket[] = []
  url: string
  readyState = 0
  onopen: (() => void) | null = null
  onmessage: ((ev: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }
  close() {
    this.readyState = 3
    this.onclose?.()
  }
  // Test helpers (not part of the WebSocket API):
  serverOpen() {
    this.readyState = 1
    this.onopen?.()
  }
  serverSend(obj: unknown) {
    this.onmessage?.({ data: JSON.stringify(obj) })
  }
}

const latest = () => MockWebSocket.instances.at(-1)!

beforeEach(() => {
  MockWebSocket.instances = []
  vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('activityFeedUrl', () => {
  it('maps http → ws and strips a trailing slash', () => {
    expect(activityFeedUrl('http://localhost:8000')).toBe(
      'ws://localhost:8000/ws/agents/activity/',
    )
    expect(activityFeedUrl('http://localhost:8000/')).toBe(
      'ws://localhost:8000/ws/agents/activity/',
    )
  })
  it('maps https → wss', () => {
    expect(activityFeedUrl('https://api.example.com')).toBe(
      'wss://api.example.com/ws/agents/activity/',
    )
  })
})

describe('useAgentActivity', () => {
  it('connects, ignores the ready frame, and buffers events newest-first', () => {
    const { result } = renderHook(() => useAgentActivity())

    expect(result.current.connected).toBe(false)
    const ws = latest()
    expect(ws.url).toBe('ws://localhost:8000/ws/agents/activity/')

    act(() => ws.serverOpen())
    expect(result.current.connected).toBe(true)

    // The control envelope is not an activity event.
    act(() => ws.serverSend({ type: 'ready', feed: 'agents-activity' }))
    expect(result.current.events).toHaveLength(0)

    act(() => ws.serverSend({ type: 'agent_call', agent: 'LegalAnalyst' }))
    act(() => ws.serverSend({ type: 'graph_query', agent: 'PrecedentHunter' }))

    expect(result.current.events).toHaveLength(2)
    // Newest first.
    expect(result.current.events[0].agent).toBe('PrecedentHunter')
    expect(result.current.events[1].agent).toBe('LegalAnalyst')
    expect(result.current.lastEventAt).not.toBeNull()
  })

  it('caps the buffer at `max`', () => {
    const { result } = renderHook(() => useAgentActivity({ max: 3 }))
    const ws = latest()
    act(() => ws.serverOpen())
    for (let i = 0; i < 5; i++) {
      act(() => ws.serverSend({ type: 'agent_call', agent: `a${i}` }))
    }
    expect(result.current.events).toHaveLength(3)
    expect(result.current.events[0].agent).toBe('a4')
  })

  it('flips connected to false on close', () => {
    const { result } = renderHook(() => useAgentActivity())
    const ws = latest()
    act(() => ws.serverOpen())
    expect(result.current.connected).toBe(true)
    act(() => ws.close())
    expect(result.current.connected).toBe(false)
  })

  it('does not open a socket when disabled', () => {
    renderHook(() => useAgentActivity({ enabled: false }))
    expect(MockWebSocket.instances).toHaveLength(0)
  })

  it('tears the socket down on unmount', () => {
    const { unmount } = renderHook(() => useAgentActivity())
    const ws = latest()
    act(() => ws.serverOpen())
    const spy = vi.spyOn(ws, 'close')
    unmount()
    expect(spy).toHaveBeenCalled()
  })
})
