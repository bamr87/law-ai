/**
 * The key a spec needs when it talks to the API *directly* (spec 051).
 *
 * The app itself never sends one any more: since BL-20260430-07 the browser
 * calls a same-origin Next proxy and the server attaches a key the bundle
 * cannot see. But several specs bypass the app on purpose — a Playwright
 * `request` fixture asserting a router's response, an in-page `fetch` or
 * `WebSocket` proving the transport works — and those calls are as
 * unauthenticated as any other client.
 *
 * `make test-e2e E2E_AGENT_API_KEY=…` gates the stack; with it unset the
 * helpers below are no-ops, which is the default posture.
 */

export const API_KEY = process.env.E2E_AGENT_API_KEY ?? ''

/** Headers for a direct request to the backend. Empty when the stack is open. */
export const apiHeaders = (): Record<string, string> =>
  API_KEY ? { 'X-API-Key': API_KEY } : {}

/**
 * Query suffix for a URL the browser opens itself.
 *
 * A WebSocket handshake cannot carry a custom header from a browser, so the
 * consumer accepts `?api_key=` as well (`law_ai/agentsapi/consumers.py`).
 */
export const apiQuery = (): string =>
  API_KEY ? `?api_key=${encodeURIComponent(API_KEY)}` : ''
