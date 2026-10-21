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
| `e2e` | `mcr.microsoft.com/playwright:v1.64.1-noble` | Browsers and driver are versioned together; the image tag must equal the `@playwright/test` version in `frontend/package-lock.json`, and `tests/test_e2e_harness.py` fails the build when they drift. |
| `frontend/e2e/proxy.mjs` | A ~40-line TCP forwarder started as Playwright's `webServer` | The page's origin has to be `localhost:3000` for Next dev, and `NEXT_PUBLIC_WS_URL` points the agent socket at `ws://localhost:8000` (a route handler cannot upgrade a connection, so the socket bypasses the REST proxy). Inside a container "localhost" is the container, so this maps `localhost:3000 → frontend` and `localhost:8000 → backend-e2e`. Plain TCP, so WebSockets ride through untouched — which is the entire point of the harness. |

`seed_admin` (in `backend-e2e`'s boot command) provisions the admin login, and `make test-e2e` runs `seed_review_queue --reset` so the HITL spec always has one fresh, uncommitted quarantine row to approve. It also runs `seed_analysis_run`, which writes one finished analysis (`an-e2e-demo`): the sidecar's unreachable Ollama can only ever produce the degraded engine-state panel, so replaying a persisted run at `/analysis?id=an-e2e-demo` is the only way to assert the healthy render — the IRAC brief, the precedent list and the trace-id copy control — without billing a model. It is also the only gated API call a visit to `/analysis` makes, which is what stops `api-auth.spec.ts`'s assertions for that page from passing vacuously.

## What the specs cover

| Spec | Covers | Item |
|---|---|---|
| `smoke.spec.ts` | Every module route renders with no failed API call | BL-20260811-16 |
| `analysis-stream.spec.ts` | A real WebSocket to `/ws/agents/<id>` receives `ready → agent_step → complete`, in order, agreeing with the REST body; the UI's own socket carries a run; a malformed stream id joins no group | BL-20260811-16 |
| `analysis.spec.ts` | Form fill → live run → the engine-state panel the pinned sidecar really produces; and a persisted run replayed at `?id=` for the IRAC brief, the precedents and the trace-id copy | BL-20260429-27 |
| `api-auth.spec.ts` | All four feature pages against an ungated and a gated API — each asserted to have actually reached its own router — wrong-key rejection across all four scopes (`agent`, `analysis`, `graph`, `lsat`), and proof the key never reaches the bundle | BL-20260430-11 |
| `shell-sticky.spec.ts` | One scroller, chrome that does not move, a header that condenses, a toolbar parked beneath it — measured at two viewports | BL-20260831-05 |
| `a11y.spec.ts` | axe-core WCAG 2.1 AA over all seven catalog routes (`/matters` included), plus tab-order checks. **Runs on every PR touching `frontend/`** via the `a11y` job in `.github/workflows/ci.yml`, not only nightly | BL-20260831-09 |
| `admin-hitl.spec.ts` | Admin login → quarantine changelist → approve + commit → the case appears via `/api/graph` | BL-20260503-17 |
| `proxy-origin.spec.ts` | Every API call four fetching routes make is same-origin `/api/backend/...` (a hard-coded backend origin in a component is how the shared key reached the bundle), plus `/agents/reviews`: nav registration, render, and a served — not denied — trip through the proxy | BL-20260905-26, BL-20260906-05 |
| `graph-keyboard.spec.ts` | Arrow keys cycle the citation canvas's nodes and Enter selects one, in a real browser with a real Cytoscape `<canvas>` (jsdom renders none, so the RTL suite can only assert `tabIndex` and the label); the graph comes from `page.route` fixtures, not from Neo4j | BL-20260906-54 |
| `lsat-static/e2e/responsive.spec.ts` | The static site's header heights, 44px targets, overflow and sticky passage column at 390px and 1280px | BL-20260901-03 |

## The accessibility baseline

The catalog routes carry pre-existing colour-contrast debt — a palette that puts `text-slate-500` on `bg-slate-950`. Failing every route on day one would mean the gate gets switched off within a week, so `frontend/e2e/a11y-baseline.json` records, per route and per rule, the failure *signatures* already accepted. A contrast signature is the colour pair plus the type size and weight (`#64748b on #020617 @ 12px 400`); every other rule signs with the element's selector, positional indices erased.

Two things fail the gate: **a rule id not in the baseline**, and **a signature not in the baseline, even under a rule id that is**. The second is what makes contrast a real check rather than a permanent amnesty — text in a colour pair nobody has accepted yet is a new signature, so a PR that introduces low-contrast text goes red. A signature that stops firing is a win and the file should be re-recorded without it:

```bash
E2E_A11Y_UPDATE_BASELINE=1 make test-e2e E2E_ARGS='e2e/a11y.spec.ts'
```

Node *counts* are triage information, not an assertion: several offending elements are rows of live data (the backlog list, the agent-runs list), so a count moves with the database and would flake nightly. Signatures do not — twenty rows sharing one bad colour pair are one signature.

The residual limit, stated plainly so nobody over-reads the gate: re-using an **already-baselined** colour pair on new text does not fail. Closing that needs the debt itself paid off and the baseline emptied, not a stricter gate on top of it.

## The driver skill, and why its launch logic stays there

`.claude/skills/run-law-ai/driver.sh` also starts a stack — a throwaway `docker compose run --no-deps` API container plus, with `FRONTEND=1`, a throwaway Next container — and `BL-20260615-04` asked whether that launch logic should graduate into `scripts/` for this suite to reuse. It should not, and this is the record.

`make test-e2e` starts the compose services themselves (`--profile e2e up -d --wait frontend backend-e2e`) against real Postgres, Neo4j and Redis, leaves them up for `make test-e2e-down`, and points the frontend at the pinned-degraded sidecar through `FRONTEND_BACKEND_URL`. The driver starts two disposable containers with no databases at all, its own offline LLM, and tears them down on exit. Nothing about the two launches is the same except the word "docker", so a shared helper would abstract over five differences for one caller. The suite does not want the driver's launch logic; see `.claude/skills/run-law-ai/SKILL.md` § "Should the launch logic move into `scripts/`?" for the table.

## The static site

`lsat-static` has no server, so its harness serves the built export itself (`lsat-static/e2e/serve.mjs`) under the same base path GitHub Pages uses. `make lsat-static-e2e` builds `out/` first, then runs the suite in the pinned Playwright image. The measurements it makes — header 136px → ≤85px at 390px, ~60px condensed, off-screen past 220px of scroll, restored on focus, 44px targets, a sticky passage column at 1280px — are exactly the numbers specs/047 T-013/T-014 recorded by hand.

## What this harness is not

It is not part of `make test`. A full-stack boot plus a browser image is minutes, and putting that in the inner loop buys a slower loop for coverage the contract test already gives cheaply. Run it nightly, before a release, and whenever you touch the shell, the stream, or the API surface.

One spec is the exception in CI: `a11y.spec.ts` runs on every pull request that touches `frontend/` (the `a11y` job in `.github/workflows/ci.yml`), because a contrast or focus-order regression found a week later has already shipped. That job reclaims the runner's preinstalled toolchains before building — the nightly had to drop from daily to weekly after 37 consecutive runs died with 0 MB free — and `api-auth.spec.ts` gets a second nightly leg with `E2E_AGENT_API_KEY` set, since its gated half is skipped whenever that variable is empty.

It also never calls a paid model — provided the frontend is pointed at `backend-e2e`, which is why `make test-e2e` recreates it rather than reusing whatever `make dev` left running. Every path it exercises is either rule-based (eyecite extraction, the admin approval) or deliberately degraded (the pinned-unreachable Ollama). If a spec starts needing a real model to pass, that is a bug in the spec.
