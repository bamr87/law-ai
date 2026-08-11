/**
 * Live agent-run stream subscriber (spec 032 / BL-20260810-06).
 *
 * The ordering matters and is the whole point: the caller generates a
 * `stream_id`, subscribes, waits for `ready`, and only THEN posts the
 * analysis. Keying the channel on the server-generated analysis id made
 * streaming impossible — the client learned the id from the response, by
 * which time the run was over.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000'

export type AgentStepEvent = {
  type: 'agent_step'
  agent: string
  analysis_id: string
  trace_id: string | null
  latency_ms: number
  confidence: number
  degraded?: boolean
}

export type AgentCompleteEvent = {
  type: 'complete'
  analysis_id: string
  confidence: number
  requires_human_review: boolean
}

export type AgentReadyEvent = { type: 'ready'; run_id: string }

export type AgentStreamEvent =
  | AgentReadyEvent
  | AgentStepEvent
  | AgentCompleteEvent

/** Browser-safe unique id — `crypto.randomUUID` is not in older jsdom. */
export function newStreamId(): string {
  const uuid =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`
  // Must satisfy the server's ^[A-Za-z0-9._-]{1,64}$ contract.
  return `run-${uuid}`.replace(/[^A-Za-z0-9._-]/g, '-').slice(0, 64)
}

export function agentStreamUrl(streamId: string): string {
  const base = API_BASE.replace(/^http/, 'ws').replace(/\/$/, '')
  // A WebSocket handshake cannot carry custom headers from a browser, so the
  // key rides in the query string (the consumer accepts either).
  const key = process.env.NEXT_PUBLIC_AGENT_API_KEY
  const query = key ? `?api_key=${encodeURIComponent(key)}` : ''
  return `${base}/ws/agents/${streamId}${query}`
}

/**
 * Open a stream and resolve once the server confirms the subscription.
 *
 * Resolving on `ready` (rather than on `open`) is deliberate: the group
 * join happens server-side during connect, so posting before `ready`
 * reintroduces the very race this design removes.
 */
export function openAgentStream(
  streamId: string,
  onEvent: (event: AgentStreamEvent) => void,
  { timeoutMs = 3000 }: { timeoutMs?: number } = {},
): Promise<WebSocket> {
  return new Promise((resolve, reject) => {
    let socket: WebSocket
    try {
      socket = new WebSocket(agentStreamUrl(streamId))
    } catch (err) {
      reject(err)
      return
    }

    const timer = setTimeout(() => {
      reject(new Error('agent stream: timed out waiting for ready'))
      socket.close()
    }, timeoutMs)

    socket.onmessage = (message) => {
      let parsed: AgentStreamEvent
      try {
        parsed = JSON.parse(String(message.data)) as AgentStreamEvent
      } catch {
        return // ignore non-JSON frames rather than tearing down the stream
      }
      if (parsed.type === 'ready') {
        clearTimeout(timer)
        resolve(socket)
      }
      onEvent(parsed)
    }

    socket.onerror = () => {
      clearTimeout(timer)
      reject(new Error('agent stream: connection failed'))
    }
  })
}
