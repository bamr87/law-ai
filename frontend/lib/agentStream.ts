/**
 * Live agent-run stream subscriber (spec 032 / BL-20260810-06).
 *
 * The ordering matters and is the whole point: the caller generates a
 * `stream_id`, subscribes, waits for `ready`, and only THEN posts the
 * analysis. Keying the channel on the server-generated analysis id made
 * streaming impossible — the client learned the id from the response, by
 * which time the run was over.
 */

/**
 * Where the socket lives. Not `API_BASE`: REST now goes through the
 * same-origin proxy (a relative path with no scheme), and a WebSocket needs an
 * absolute `ws://` origin — a route handler cannot upgrade a connection, so
 * the socket still talks to the backend directly (BL-20260430-07).
 *
 * Order: an explicit `NEXT_PUBLIC_WS_URL` (a trailing `/ws` is tolerated,
 * since that is how `.env.example` has always written it), then an absolute
 * API base, then this page's own origin, then the local default.
 */
function resolveWsOrigin(): string {
  const explicit = process.env.NEXT_PUBLIC_WS_URL
  if (explicit) return explicit.replace(/\/$/, '').replace(/\/ws$/, '')
  const api = process.env.NEXT_PUBLIC_API_BASE_URL
  if (api && /^https?:\/\//.test(api)) {
    return api.replace(/^http/, 'ws').replace(/\/$/, '')
  }
  if (typeof window !== 'undefined') {
    return window.location.origin.replace(/^http/, 'ws')
  }
  return 'ws://localhost:8000'
}

export type AgentStepEvent = {
  type: 'agent_step'
  agent: string
  analysis_id: string
  trace_id: string | null
  latency_ms: number
  confidence: number
  degraded?: boolean
  /** Server-assigned position in the run's event buffer (BL-20260811-14). */
  seq?: number
}

/**
 * The terminal event of a run. Every producer sends one — analysis names the
 * `analysis_id`, the tutor the `question_id` — which is what tells the client
 * the stream is over and no reconnect is needed.
 */
export type AgentCompleteEvent = {
  type: 'complete'
  analysis_id?: string
  question_id?: string
  model?: string
  cached?: boolean
  confidence: number
  requires_human_review: boolean
  seq?: number
}

/**
 * One coaching delta from the LSAT tutor (BL-20260503-03).
 *
 * The same socket the analysis studio uses: spec 011 and ADR 0001 chose
 * Channels as the repo-wide push transport, so the tutor streams over it
 * rather than opening a second SSE surface.
 */
export type AgentTokenEvent = {
  type: 'tutor_token'
  question_id: string
  text: string
  model: string
  seq?: number
}

/**
 * A named stage of a long-running job — the tutor's tier attempts
 * (BL-20260811-15) and the autonomy cycle's boundaries. Progress, not data:
 * the REST response is still the result.
 */
export type AgentStageEvent = {
  type: 'tutor_step' | 'autonomy_step'
  stage: string
  model?: string
  question_id?: string
  cycle_id?: string
  seq?: number
}

/**
 * One delta of the analysis IRAC pass, while the model is still writing
 * (BL-20260905-11).
 *
 * The `/api/analysis` run used to send nothing between "submitted" and
 * "finished" — 56-103s of blank page on the slower tiers. `chars` is the
 * running total the server has produced, so a client can show progress
 * without rendering half-written JSON.
 */
export type AnalysisTokenEvent = {
  type: 'analysis_token'
  agent: string
  text: string
  chars: number
  analysis_id?: string
  model?: string
  seq?: number
}

/** `since` echoes the replay cursor the server understood on this handshake. */
export type AgentReadyEvent = { type: 'ready'; run_id: string; since?: number }

export type AgentStreamEvent =
  | AgentReadyEvent
  | AgentStepEvent
  | AgentStageEvent
  | AgentTokenEvent
  | AnalysisTokenEvent
  | AgentCompleteEvent

/**
 * Where the *connection* stands, as opposed to what the run is producing
 * (BL-20260905-79).
 *
 * The reconnect loop below was entirely silent: a dropped socket looked
 * exactly like a model that had stopped writing, so a learner watching a
 * half-finished walkthrough had no way to tell "still coming" from "stuck".
 *
 * - `live` — handshaked; frames are arriving. Sent on every `ready`, so it is
 *   also the signal that a reconnect succeeded.
 * - `reconnecting` — the socket dropped mid-run and a retry is scheduled.
 * - `lost` — the retries are spent; nothing more will arrive on this stream.
 *   The REST response every caller awaits is still authoritative.
 */
export type AgentStreamStatus = 'live' | 'reconnecting' | 'lost'

/** Browser-safe unique id — `crypto.randomUUID` is not in older jsdom. */
export function newStreamId(): string {
  const uuid =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`
  // Must satisfy the server's ^[A-Za-z0-9._-]{1,64}$ contract.
  return `run-${uuid}`.replace(/[^A-Za-z0-9._-]/g, '-').slice(0, 64)
}

export function agentStreamUrl(
  streamId: string,
  ticket?: string | null,
  { since, replay }: { since?: number; replay?: boolean } = {},
): string {
  const base = resolveWsOrigin()
  // A WebSocket handshake cannot carry custom headers from a browser. It used
  // to carry the shared API key, which meant the key had to be in the bundle;
  // it now carries a short-lived, stream-scoped ticket minted by
  // `/api/ws-ticket` from the server-only key (BL-20260430-07). The consumer
  // accepts a ticket, a raw key (non-browser clients), or a header.
  const params = new URLSearchParams()
  if (ticket) params.set('ticket', ticket)
  // The reconnect cursor (BL-20260811-14). `replay` asks for catch-up from
  // the start of the buffer, which the server refuses without it so that a
  // fresh subscriber reusing a stream id is never handed an old run.
  if (since !== undefined && since > 0) params.set('since', String(since))
  if (replay) params.set('replay', '1')
  const query = params.toString()
  return `${base}/ws/agents/${streamId}${query ? `?${query}` : ''}`
}

/**
 * Ask this app's own server for a ticket for `streamId`.
 *
 * `null` means "none needed": with no `AGENT_API_KEY` configured the consumer
 * is open, which is the local-first default. A failure to reach the ticket
 * route is also `null` — the socket then tries unauthenticated and is closed
 * by the consumer with 4401 if a key *was* required, which is a clearer
 * failure than never opening at all.
 */
export async function fetchStreamTicket(
  streamId: string,
): Promise<string | null> {
  try {
    const res = await fetch(
      `/api/ws-ticket?stream=${encodeURIComponent(streamId)}`,
      { cache: 'no-store' },
    )
    if (!res.ok) return null
    const body = (await res.json()) as { ticket?: string | null }
    return body.ticket ?? null
  } catch {
    return null
  }
}

/**
 * Open a stream and resolve once the server confirms the subscription.
 *
 * Resolving on `ready` (rather than on `open`) is deliberate: the group
 * join happens server-side during connect, so posting before `ready`
 * reintroduces the very race this design removes.
 *
 * The stream survives a dropped socket (BL-20260811-14). Every event carries
 * a server-assigned `seq`; when the connection closes before the run's
 * `complete` event, this reconnects with `?since=<last seq>` and the server
 * replays what was missed, so a laptop lid or a flaky tunnel costs a few
 * seconds rather than the whole trace. Duplicate sequences are dropped here,
 * so a consumer never sees the same step twice.
 *
 * The resolved value is therefore a handle on the *stream*, not on one TCP
 * connection: calling `close()` on it ends the stream for good, reconnection
 * included, which is exactly what a caller's `finally { socket.close() }`
 * means.
 *
 * The `ready` handshake itself gets more than one go (BL-20260905-21). A cold
 * Channels layer or a loaded dev server routinely takes longer than the first
 * window, and every caller treats a rejection as "run it unstreamed", so
 * losing that race used to cost the whole live trace silently. The window is
 * now 5s and a timed-out handshake is retried once on a fresh socket before
 * the caller gives up.
 */
export async function openAgentStream(
  streamId: string,
  onEvent: (event: AgentStreamEvent) => void,
  {
    timeoutMs = 5000,
    maxReconnects = 4,
    reconnectBaseMs = 500,
    handshakeRetries = 1,
    onStatus,
  }: {
    timeoutMs?: number
    maxReconnects?: number
    reconnectBaseMs?: number
    handshakeRetries?: number
    /**
     * Connection state, for a caller that wants to say "reconnecting…" rather
     * than leave a stalled trace looking finished (BL-20260905-79).
     */
    onStatus?: (status: AgentStreamStatus) => void
  } = {},
): Promise<WebSocket> {
  // One round trip to this app's own server before the socket opens: the
  // credential the handshake needs cannot live in the page (BL-20260430-07).
  const ticket = await fetchStreamTicket(streamId)

  let lastSeq = 0
  let finished = false // the run sent `complete`; nothing left to catch up on
  let stopped = false // the caller closed the stream
  let attempts = 0
  let timer: ReturnType<typeof setTimeout> | null = null

  const handle = (parsed: AgentStreamEvent): boolean => {
    const seq = 'seq' in parsed ? parsed.seq : undefined
    if (typeof seq === 'number') {
      // A replayed frame the caller already saw. Dropping it here is what
      // lets a consumer append blindly instead of deduping itself.
      if (seq <= lastSeq) return false
      lastSeq = seq
    }
    if (parsed.type === 'complete') finished = true
    return true
  }

  const wire = (
    socket: WebSocket,
    onReady: ((socket: WebSocket) => void) | null,
    onFail: ((error: Error) => void) | null,
  ) => {
    socket.onmessage = (message) => {
      let parsed: AgentStreamEvent
      try {
        parsed = JSON.parse(String(message.data)) as AgentStreamEvent
      } catch {
        return // ignore non-JSON frames rather than tearing down the stream
      }
      if (parsed.type === 'ready') {
        if (timer) clearTimeout(timer)
        attempts = 0 // a completed handshake resets the backoff
        // Also how a caller learns a reconnect took: `ready` is the only
        // frame the server sends on every successful handshake.
        onStatus?.('live')
        onReady?.(socket)
      }
      if (handle(parsed)) onEvent(parsed)
    }

    socket.onerror = () => {
      if (timer) clearTimeout(timer)
      onFail?.(new Error('agent stream: connection failed'))
    }

    socket.onclose = () => {
      if (stopped || finished) return
      if (attempts >= maxReconnects) {
        // The retries are spent. Say so once — a caller that shows
        // "reconnecting…" forever is lying about a stream that is over.
        onStatus?.('lost')
        return
      }
      onStatus?.('reconnecting')
      const delay = reconnectBaseMs * 2 ** attempts
      attempts += 1
      setTimeout(() => {
        if (stopped || finished) return
        reconnect()
      }, delay)
    }
  }

  const stop = (socket: WebSocket) => {
    // Bind the *instance's* own method: a test double's `close` is an own
    // property, and reaching through WebSocket.prototype would miss it.
    const close = socket.close.bind(socket)
    socket.close = () => {
      stopped = true
      if (timer) clearTimeout(timer)
      close()
    }
  }

  const reconnect = () => {
    let socket: WebSocket
    try {
      socket = new WebSocket(
        agentStreamUrl(streamId, ticket, { since: lastSeq, replay: true }),
      )
    } catch {
      return // the environment lost WebSocket; the REST result still lands
    }
    stop(socket)
    wire(socket, null, null)
  }

  const handshake = (isLastTry: boolean): Promise<WebSocket> =>
    new Promise((resolve, reject) => {
      let socket: WebSocket
      try {
        socket = new WebSocket(agentStreamUrl(streamId, ticket))
      } catch (err) {
        reject(err)
        return
      }
      // Captured before `stop` wraps it: abandoning a socket for a retry must
      // close *that* connection without marking the whole stream stopped.
      const rawClose = socket.close.bind(socket)

      timer = setTimeout(() => {
        if (isLastTry) {
          socket.close() // wrapped: ends the stream, reconnection included
        } else {
          // Detach first, or this close would look like a dropped connection
          // and schedule a reconnect alongside the retry socket.
          socket.onmessage = null
          socket.onerror = null
          socket.onclose = null
          rawClose()
        }
        reject(new Error('agent stream: timed out waiting for ready'))
      }, timeoutMs)

      stop(socket)
      wire(socket, resolve, reject)
    })

  let lastError: unknown
  for (let tryNo = 0; tryNo <= Math.max(0, handshakeRetries); tryNo += 1) {
    try {
      return await handshake(tryNo >= Math.max(0, handshakeRetries))
    } catch (err) {
      lastError = err
      // Only the handshake race is worth a second socket; a refused or failed
      // connection would fail again exactly the same way.
      if (!(err instanceof Error && err.message.includes('timed out'))) throw err
      attempts = 0
      stopped = false
    }
  }
  throw lastError
}
