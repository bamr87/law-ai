/**
 * Ops-dashboard push channel (BL-20260429-16).
 *
 * The dashboard used to poll six REST endpoints every five seconds whether or
 * not anything had changed — 72 requests a minute per open tab, multiplied by
 * every reviewer watching. This socket carries a *change notification*, not
 * the data: on `runs_changed` the dashboard re-fetches through the same REST
 * endpoints it always used, so there is exactly one source of truth and the
 * push is a pure optimisation.
 *
 * Because it is only an optimisation, every failure path degrades to polling
 * rather than to a broken screen: no WebSocket in the environment (jsdom, an
 * old browser), a refused handshake, a socket that closes mid-session — the
 * caller keeps its interval and carries on.
 */
import { agentStreamUrl, fetchStreamTicket } from '@/lib/agentStream'

/** The reserved stream id the backend signs an ops ticket against. */
const OPS_STREAM_ID = 'ops'

export type OpsChangeEvent = {
  /**
   * The only kind the backend emits (BL-20260905-76). `metrics_changed` was
   * declared on both sides and never sent: the metrics endpoint aggregates the
   * same `agent_call` events a run notification already covers.
   */
  type: 'runs_changed'
  agent?: string
  trace_id?: string
}

export type OpsReadyEvent = { type: 'ready'; channel: string }

export type OpsEvent = OpsReadyEvent | OpsChangeEvent

/** `.../ws/agents/ops`, reusing the run stream's origin and ticket rules. */
export function opsStreamUrl(ticket?: string | null): string {
  return agentStreamUrl(OPS_STREAM_ID, ticket)
}

export type OpsStreamHandle = {
  /** Tear the socket down and stop reconnecting. */
  close: () => void
}

/**
 * Subscribe to dashboard change notifications.
 *
 * Resolves synchronously with a handle — the caller never awaits a socket to
 * render. `onChange` fires per change notification; `onStatus` reports whether
 * the push channel is live, which is what tells the caller whether it still
 * needs its polling interval.
 *
 * Reconnection is bounded exponential backoff from one second, capped at
 * thirty: a dashboard left open overnight against a down backend must not
 * turn into a reconnect storm.
 */
export function openOpsStream(
  onChange: (event: OpsChangeEvent) => void,
  {
    onStatus,
    maxBackoffMs = 30_000,
  }: {
    onStatus?: (connected: boolean) => void
    maxBackoffMs?: number
  } = {},
): OpsStreamHandle {
  let socket: WebSocket | null = null
  let timer: ReturnType<typeof setTimeout> | null = null
  let attempt = 0
  let closed = false

  const scheduleRetry = () => {
    if (closed) return
    const delay = Math.min(maxBackoffMs, 1000 * 2 ** attempt)
    attempt += 1
    timer = setTimeout(() => void connect(), delay)
  }

  const connect = async () => {
    if (closed) return
    if (typeof WebSocket === 'undefined') {
      // jsdom and non-browser runtimes: the caller keeps polling forever,
      // which is exactly the pre-push behaviour.
      onStatus?.(false)
      return
    }
    let ticket: string | null = null
    try {
      ticket = await fetchStreamTicket(OPS_STREAM_ID)
    } catch {
      ticket = null
    }
    if (closed) return
    try {
      socket = new WebSocket(opsStreamUrl(ticket))
    } catch {
      onStatus?.(false)
      scheduleRetry()
      return
    }

    socket.onmessage = (message) => {
      let parsed: OpsEvent
      try {
        parsed = JSON.parse(String(message.data)) as OpsEvent
      } catch {
        return // ignore non-JSON frames rather than tearing down the stream
      }
      if (parsed.type === 'ready') {
        attempt = 0 // a completed handshake resets the backoff
        onStatus?.(true)
        return
      }
      onChange(parsed)
    }
    socket.onerror = () => onStatus?.(false)
    socket.onclose = () => {
      socket = null
      onStatus?.(false)
      scheduleRetry()
    }
  }

  void connect()

  return {
    close: () => {
      closed = true
      if (timer) clearTimeout(timer)
      socket?.close()
      socket = null
    },
  }
}
