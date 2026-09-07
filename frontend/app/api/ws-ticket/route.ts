import { createHmac } from 'crypto'
import { NextResponse } from 'next/server'

/**
 * Mint a short-lived ticket for one agent-run WebSocket (BL-20260430-07).
 *
 * REST calls go through `/api/backend`, which attaches the API key
 * server-side. A WebSocket handshake cannot carry a custom header from a
 * browser and cannot be proxied by a route handler, so the socket needs
 * *something* in its query string. A ticket rather than the key itself: it is
 * signed for one stream id, expires in a minute, and tells the consumer only
 * that a holder of `AGENT_API_KEY` vouched for this stream.
 *
 * The format is defined once, executably, in `law_ai/core/ws_ticket.py`:
 *
 *     "<expiry-unix>.<hex HMAC-SHA256(key, `${streamId}.${expiry}`)>"
 *
 * With no `AGENT_API_KEY` configured — the local-first default — there is
 * nothing to prove, so the answer is `{ ticket: null }` and the socket
 * connects unauthenticated, exactly as the REST routers stay open.
 */
const TTL_SECONDS = 60

/** Same contract the consumer enforces: `^[A-Za-z0-9._-]{1,64}$`. */
const STREAM_ID = /^[A-Za-z0-9._-]{1,64}$/

export async function GET(request: Request) {
  const streamId = new URL(request.url).searchParams.get('stream') ?? ''
  if (!STREAM_ID.test(streamId)) {
    return NextResponse.json({ detail: 'Invalid stream id' }, { status: 400 })
  }

  const key = process.env.AGENT_API_KEY
  if (!key) return NextResponse.json({ ticket: null })

  const expiry = Math.floor(Date.now() / 1000) + TTL_SECONDS
  const mac = createHmac('sha256', key)
    .update(`${streamId}.${expiry}`)
    .digest('hex')

  return NextResponse.json(
    { ticket: `${expiry}.${mac}`, expiresAt: expiry },
    // A ticket is per-request and short-lived; a cached one is a bug.
    { headers: { 'Cache-Control': 'no-store' } },
  )
}

export const dynamic = 'force-dynamic'
