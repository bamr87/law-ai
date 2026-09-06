import { NextResponse } from 'next/server'

/**
 * Server-side proxy to the Django API (BL-20260430-07).
 *
 * The browser used to call the backend directly with
 * `X-API-Key: ${NEXT_PUBLIC_AGENT_API_KEY}` — and anything `NEXT_PUBLIC_*` is
 * compiled into the page, so the shared key was readable by anyone who opened
 * the bundle (docs/security.md, spec 008 R-2). Every browser→backend call now
 * goes to this same-origin route instead, and the key is attached here, in the
 * Node process, from a server-only `AGENT_API_KEY`.
 *
 * It is a forwarder, not an API: the path after `/api/backend` is the backend
 * path, the method, query string, body and content type ride through
 * unchanged, and the upstream status and body come back as they are. Nothing
 * here decides what the backend means — that would be a second implementation
 * of the API to keep in sync.
 */
const BACKEND =
  process.env.BACKEND_INTERNAL_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL_INTERNAL ||
  'http://backend:8000'

/** Hop-by-hop and identity headers the upstream must set for itself. */
const STRIP_REQUEST = new Set([
  'host',
  'connection',
  'content-length',
  'x-api-key',
  'cookie',
])

const STRIP_RESPONSE = new Set([
  'content-encoding',
  'content-length',
  'transfer-encoding',
  'connection',
])

type Params = { params: Promise<{ path: string[] }> }

async function forward(request: Request, { params }: Params) {
  const { path } = await params
  const target = new URL(request.url)
  const upstream = `${BACKEND.replace(/\/$/, '')}/${path.join('/')}${target.search}`

  const headers = new Headers()
  request.headers.forEach((value, name) => {
    if (!STRIP_REQUEST.has(name.toLowerCase())) headers.set(name, value)
  })
  // The one header the browser must never be able to set for itself.
  const key = process.env.AGENT_API_KEY
  if (key) headers.set('X-API-Key', key)

  const method = request.method.toUpperCase()
  const body =
    method === 'GET' || method === 'HEAD' ? undefined : await request.arrayBuffer()

  let response: Response
  try {
    response = await fetch(upstream, {
      method,
      headers,
      body,
      cache: 'no-store',
      redirect: 'manual',
    })
  } catch {
    // A dead backend is a 502 from the proxy, not an unhandled exception that
    // renders the Next error page in place of the screen's own error state.
    return NextResponse.json(
      { detail: 'Backend unreachable' },
      { status: 502 },
    )
  }

  const out = new Headers()
  response.headers.forEach((value, name) => {
    if (!STRIP_RESPONSE.has(name.toLowerCase())) out.set(name, value)
  })

  return new NextResponse(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: out,
  })
}

export const GET = forward
export const POST = forward
export const PUT = forward
export const PATCH = forward
export const DELETE = forward
export const HEAD = forward

/** Never prerender or cache a proxy. */
export const dynamic = 'force-dynamic'
