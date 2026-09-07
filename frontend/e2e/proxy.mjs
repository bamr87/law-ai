// Loopback → compose-network forwarder for the e2e browser (spec 051).
//
// Next dev is happiest when the page's origin is `localhost:3000`, the app's
// REST proxy route forwards to the backend from inside that container, and
// `NEXT_PUBLIC_WS_URL` points the agent stream at `ws://localhost:8000` (a
// route handler cannot upgrade a connection, so the socket talks to the API
// directly). Inside the e2e container "localhost" is the container itself, so
// this script listens on those two loopback ports and pipes each TCP
// connection to the real service on the compose network (`frontend:3000`,
// `backend-e2e:8000`). Plain TCP, so WebSockets ride through untouched —
// which is the whole point of the harness: jsdom has no WebSocket, this
// browser does.
//
// playwright.config.ts starts it as the `webServer`; it does nothing when the
// E2E_*_UPSTREAM variables are unset (a developer's own browser needs no
// forwarding).
import net from 'node:net'

const pairs = [
  [3000, process.env.E2E_FRONTEND_UPSTREAM],
  [8000, process.env.E2E_BACKEND_UPSTREAM],
]

let listening = 0
for (const [port, upstream] of pairs) {
  if (!upstream) continue
  const [host, upstreamPort] = upstream.split(':')
  const server = net.createServer((client) => {
    const up = net.connect(Number(upstreamPort ?? port), host)
    client.pipe(up)
    up.pipe(client)
    client.on('error', () => up.destroy())
    up.on('error', () => client.destroy())
  })
  server.on('error', (err) => {
    console.error(`e2e proxy: cannot listen on :${port} — ${err.message}`)
    process.exit(1)
  })
  server.listen(port, () => {
    listening += 1
    console.log(`e2e proxy: localhost:${port} → ${upstream}`)
  })
}

if (listening === 0 && pairs.every(([, upstream]) => !upstream)) {
  console.error(
    'e2e proxy: E2E_FRONTEND_UPSTREAM / E2E_BACKEND_UPSTREAM unset — nothing to forward',
  )
  process.exit(1)
}
