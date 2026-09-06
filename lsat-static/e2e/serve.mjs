// Static file server for the exported site (spec 051 / BL-20260901-03).
//
// `lsat-static` is a Next static export with no server of its own, and the
// responsive spec has to measure the *built* site — the one GitHub Pages
// publishes — not a dev server. `npx serve` is not a dependency here and this
// is 60 lines of Node, so the harness carries its own.
//
// The export is built with a base path (`/law-ai` by default, see
// next.config.mjs), so every asset URL starts with it. This strips that prefix
// and serves `out/` beneath it, which means the same server works for a build
// made with PAGES_BASE_PATH="" too.
import { createReadStream, existsSync, statSync } from 'node:fs'
import http from 'node:http'
import path from 'node:path'

const ROOT = path.resolve(process.cwd(), 'out')
const PORT = Number(process.env.E2E_PORT ?? 4321)
const RAW_BASE = process.env.PAGES_BASE_PATH ?? '/law-ai'
const BASE = RAW_BASE === '/' ? '' : RAW_BASE.replace(/\/$/, '')

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.txt': 'text/plain; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.woff2': 'font/woff2',
}

if (!existsSync(ROOT)) {
  console.error(
    `lsat-static e2e: ${ROOT} does not exist — run \`make lsat-static-build\` first`,
  )
  process.exit(1)
}

/** Map a request path to a file inside `out/`, or null if it escapes. */
function resolveFile(urlPath) {
  let rel = decodeURIComponent(urlPath.split('?')[0])
  if (BASE && (rel === BASE || rel.startsWith(`${BASE}/`))) {
    rel = rel.slice(BASE.length) || '/'
  }
  const target = path.resolve(ROOT, `.${rel}`)
  // Never serve outside the export, whatever the request says.
  if (target !== ROOT && !target.startsWith(`${ROOT}${path.sep}`)) return null
  if (existsSync(target) && statSync(target).isDirectory()) {
    return path.join(target, 'index.html')
  }
  if (existsSync(target)) return target
  // `trailingSlash: true` exports every route as <route>/index.html.
  const asDir = path.join(target, 'index.html')
  if (existsSync(asDir)) return asDir
  const asHtml = `${target}.html`
  return existsSync(asHtml) ? asHtml : null
}

http
  .createServer((req, res) => {
    const file = resolveFile(req.url ?? '/')
    if (!file) {
      res.writeHead(404, { 'content-type': 'text/plain' })
      res.end('not found')
      return
    }
    res.writeHead(200, {
      'content-type': TYPES[path.extname(file)] ?? 'application/octet-stream',
      'cache-control': 'no-store',
    })
    createReadStream(file).pipe(res)
  })
  .listen(PORT, () => {
    console.log(`lsat-static e2e: serving ${ROOT} on :${PORT}${BASE || '/'}`)
  })
