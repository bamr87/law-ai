# Browser end-to-end testing

The unit suites stop at the boundary. `frontend/__tests__/` runs in jsdom, which has no layout engine and no `WebSocket`: sticky positioning never sticks, nothing scrolls, and `__tests__/lib/agentStream.test.ts` has to stub the socket with a fake class, so the streaming path is only ever exercised through its fallback. `backend/tests/` never renders anything. Between them sat the whole of what a user actually touches — and, until spec 051, no test crossed from one side to the other.

This page describes the harness that closes that gap: what runs, how to run it, and what it deliberately does not do.

## The two halves

**The cheap half runs on every PR.** `manage.py export_api_schema` publishes the browser-facing Pydantic contracts as JSON Schema to `frontend/__tests__/fixtures/api-schema.json`; `frontend/__tests__/lib/apiContract.test.ts` compares each one against the hand-written TypeScript interface in `frontend/lib/api.ts` and against the MSW fixtures the component tests run on. A field the backend renames, drops or newly requires now fails `make test` instead of surfacing in production. `backend/tests/core/test_export_api_schema.py` fails when the checked-in fixture is stale, so the two can never quietly diverge.

**The expensive half runs nightly and on demand.** `make test-e2e` boots the stack and drives a real Chromium against it.

## Running it

```bash
make test-e2e                                   # the whole suite
make test-e2e E2E_ARGS='e2e/a11y.spec.ts'       # one spec
make test-e2e E2E_AGENT_API_KEY=s3cret          # gate the API for the auth spec
make test-e2e-typecheck                         # tsc over the specs
make test-e2e-down                              # stop the sidecars, leave `make dev` alone
```

Both e2e services sit behind the compose `e2e` profile, so `make dev`, `make test` and `make down` never see them.

## How the stack is wired

| Piece | What it is | Why |
|---|---|---|
| `backend-e2e` | A second API on the same image and databases | Its provider chain is pinned to Ollama at an unreachable address with zero retries, so `/api/analysis` takes the honest degraded path every run: deterministic `ready → agent_step → complete`, no third-party call, no bill. It also forces `AGENT_API_KEY` from `E2E_AGENT_API_KEY` so the auth spec — not the operator's `.env` — decides whether the API is gated. |
| the `frontend` service, recreated | Same image, `BACKEND_INTERNAL_URL=http://backend-e2e:8000` | Since BL-20260430-07 the browser's REST calls go through the Next same-origin proxy, so the API the UI talks to is whatever the *server* points at. Leaving that at the dev backend would route e2e analysis runs through the operator's real provider chain and bill them, which is exactly what the sidecar exists to prevent. `make test-e2e-down` puts it back. |
| `e2e` | `mcr.microsoft.com/playwright:v1.59.1-noble` | Browsers and driver are versioned together; the image tag must equal the `@playwright/test` version in `frontend/package-lock.json`, and `tests/test_e2e_harness.py` fails the build when they drift. |
| `frontend/e2e/proxy.mjs` | A ~40-line TCP forwarder started as Playwright's `webServer` | The page's origin has to be `localhost:3000` for Next dev, and `NEXT_PUBLIC_WS_URL` points the agent socket at `ws://localhost:8000` (a route handler cannot upgrade a connection, so the socket bypasses the REST proxy). Inside a container "localhost" is the container, so this maps `localhost:3000 → frontend` and `localhost:8000 → backend-e2e`. Plain TCP, so WebSockets ride through untouched — which is the entire point of the harness. |

`seed_admin` (in `backend-e2e`'s boot command) provisions the admin login, and `make test-e2e` runs `seed_review_queue --reset` so the HITL spec always has one fresh, uncommitted quarantine row to approve.

## What the specs cover

| Spec | Covers | Item |
|---|---|---|
| `smoke.spec.ts` | Every module route renders with no failed API call | BL-20260811-16 |
| `analysis-stream.spec.ts` | A real WebSocket to `/ws/agents/<id>` receives `ready → agent_step → complete`, in order, agreeing with the REST body; the UI's own socket carries a run; a malformed stream id joins no group | BL-20260811-16 |
| `analysis.spec.ts` | Form fill → result render → trace-id copy on `/analysis` | BL-20260429-27 |
| `api-auth.spec.ts` | All four feature pages against an ungated and a gated API, wrong-key rejection per router, and proof the key never reaches the bundle | BL-20260430-11 |
| `shell-sticky.spec.ts` | One scroller, chrome that does not move, a header that condenses, a toolbar parked beneath it — measured at two viewports | BL-20260831-05 |
| `a11y.spec.ts` | axe-core WCAG 2.1 AA over the six catalog routes, plus tab-order checks | BL-20260831-09 |
| `admin-hitl.spec.ts` | Admin login → quarantine changelist → approve + commit → the case appears via `/api/graph` | BL-20260503-17 |
| `lsat-static/e2e/responsive.spec.ts` | The static site's header heights, 44px targets, overflow and sticky passage column at 390px and 1280px | BL-20260901-03 |

## The accessibility baseline

The six routes carry pre-existing colour-contrast debt — a palette that puts `text-slate-500` on `bg-slate-950`. Failing every route on day one would mean the gate gets switched off within a week, so `frontend/e2e/a11y-baseline.json` records which rule ids already fire per route. **A rule id not in the baseline fails immediately.** A rule that stops firing is a win and the file should be re-recorded without it:

```bash
docker compose --profile e2e run --rm --no-deps -e E2E_A11Y_UPDATE_BASELINE=1 e2e npx playwright test e2e/a11y.spec.ts
```

The recorded node counts are triage information, not an assertion: several offending elements are rows of live data (the backlog list, the agent-runs list), so the count moves with the database while the rule-id set does not.

## The static site

`lsat-static` has no server, so its harness serves the built export itself (`lsat-static/e2e/serve.mjs`) under the same base path GitHub Pages uses. `make lsat-static-e2e` builds `out/` first, then runs the suite in the pinned Playwright image. The measurements it makes — header 136px → ≤85px at 390px, ~60px condensed, off-screen past 220px of scroll, restored on focus, 44px targets, a sticky passage column at 1280px — are exactly the numbers specs/047 T-013/T-014 recorded by hand.

## What this harness is not

It is not part of `make test`. A full-stack boot plus a browser image is minutes, and putting that in the PR gate buys a slower loop for coverage the contract test already gives cheaply. Run it nightly, before a release, and whenever you touch the shell, the stream, or the API surface.

It also never calls a paid model — provided the frontend is pointed at `backend-e2e`, which is why `make test-e2e` recreates it rather than reusing whatever `make dev` left running. Every path it exercises is either rule-based (eyecite extraction, the admin approval) or deliberately degraded (the pinned-unreachable Ollama). If a spec starts needing a real model to pass, that is a bug in the spec.
