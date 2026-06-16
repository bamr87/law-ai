'use client'

import { useEffect, useState } from 'react'

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'

/** Compact, non-sensitive frame streamed by the backend live feed (WS3).
 *
 * Mirrors `lawgraph.agentsapi.broadcast.compact_event` — the backend already
 * strips prompts/hashes, so anything here is safe to render.
 */
export interface ActivityEvent {
  type: string
  agent?: string
  model?: string
  trace_id?: string
  session_id?: string
  cycle_id?: string
  cycle_type?: string
  status?: string
  timestamp?: string
  latency_ms?: number
  confidence?: number
  [key: string]: unknown
}

export interface AgentActivityState {
  /** True while the socket is open. When false the dashboard's HTTP poll
   * remains the source of truth, so the UI degrades cleanly. */
  connected: boolean
  /** Most-recent-first ring buffer of streamed frames (capped at `max`). */
  events: ActivityEvent[]
  /** Epoch ms of the most recent frame, or `null` if none yet. */
  lastEventAt: number | null
}

/** Derive the Channels ws(s) endpoint from the HTTP API base. */
export function activityFeedUrl(base: string = API_BASE): string {
  const origin = base.replace(/^http(s?):\/\//i, (_m, s: string) => `ws${s}://`)
  return `${origin.replace(/\/$/, '')}/ws/agents/activity/`
}

const DEFAULT_MAX = 50
const MAX_BACKOFF_MS = 15_000

/**
 * Subscribe to the dashboard-wide live activity feed over a WebSocket.
 *
 * Best-effort and self-healing: on close/error it reconnects with capped
 * exponential backoff, and while disconnected the consumer should keep
 * polling. Never throws — a missing/blocked socket just yields
 * `connected: false` with an empty buffer.
 */
export function useAgentActivity(options?: {
  max?: number
  enabled?: boolean
}): AgentActivityState {
  const max = options?.max ?? DEFAULT_MAX
  const enabled = options?.enabled ?? true
  const [connected, setConnected] = useState(false)
  const [events, setEvents] = useState<ActivityEvent[]>([])
  const [lastEventAt, setLastEventAt] = useState<number | null>(null)

  useEffect(() => {
    if (!enabled) return
    if (typeof window === 'undefined' || typeof WebSocket === 'undefined') return

    let cancelled = false
    let ws: WebSocket | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let attempt = 0

    const scheduleReconnect = () => {
      if (cancelled) return
      attempt += 1
      const delay = Math.min(1000 * 2 ** Math.min(attempt, 4), MAX_BACKOFF_MS)
      reconnectTimer = setTimeout(connect, delay)
    }

    function connect() {
      if (cancelled) return
      try {
        ws = new WebSocket(activityFeedUrl())
      } catch {
        scheduleReconnect()
        return
      }
      ws.onopen = () => {
        if (cancelled) return
        attempt = 0
        setConnected(true)
      }
      ws.onmessage = (ev: MessageEvent) => {
        if (cancelled) return
        let frame: ActivityEvent
        try {
          frame = JSON.parse(String(ev.data)) as ActivityEvent
        } catch {
          return
        }
        // The `ready` envelope is a control frame, not an activity event.
        if (frame.type === 'ready') return
        setEvents((prev) => [frame, ...prev].slice(0, max))
        setLastEventAt(Date.now())
      }
      ws.onclose = () => {
        if (cancelled) return
        setConnected(false)
        scheduleReconnect()
      }
      // onerror is followed by onclose, which owns the reconnect.
      ws.onerror = () => {}
    }

    connect()

    return () => {
      cancelled = true
      if (reconnectTimer) clearTimeout(reconnectTimer)
      if (ws) {
        ws.onopen = null
        ws.onmessage = null
        ws.onclose = null
        ws.onerror = null
        try {
          ws.close()
        } catch {
          /* already closing */
        }
      }
    }
  }, [enabled, max])

  return { connected, events, lastEventAt }
}
