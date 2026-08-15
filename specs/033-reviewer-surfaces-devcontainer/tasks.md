# Tasks: Reviewer Surfaces (Live Trace, Verified Citations) + Dev Container

Spec: [spec.md](spec.md) · Plan: [plan.md](plan.md)

- [x] **T-001** — Subscribe-then-post wiring in Analysis Studio (FR-1, FR-4)
  - `newStreamId()` → `openAgentStream()` → await `ready` → POST with
    `stream_id`; socket closed in `finally` so no path leaks a connection.
- [x] **T-002** — Live trace panel (FR-2, NFR-A11Y-1)
  - `LiveTrace` renders each `agent_step` as it lands (agent, latency,
    `degraded` marker) in an `aria-live="polite"` labelled region.
- [x] **T-003** — Streaming is an enhancement, never a dependency (FR-3, NFR-RESILIENCE-1, AC-3)
  - A socket that fails to open ⇒ POST proceeds **without** `stream_id`
    and the REST response stands; the panel renders nothing rather than an
    empty box that never fills.
- [x] **T-004** — Verified-citation badges (FR-5, AC-1, AC-2)
  - Tri-state: `verified in graph` / `unverified` (+ tooltip pointing at
    the official record, so the badge is never read as "correct") / no
    badge when the backend did not report verification.
- [x] **T-005** — Dev container on the compose backend service (FR-6, AC-4)
  - `.devcontainer/devcontainer.json`: `service: backend`,
    `workspaceFolder: /app`, `overrideCommand` so daphne does not own the
    session, sanctioned extensions only, pytest discovery on, system
    interpreter (the image installs `-e`, so there is no venv), and
    `PHOENIX_COLLECTOR_ENDPOINT=""` for quiet in-editor test runs.
- [x] **T-006** — Tests (AC-1, AC-2, AC-3, AC-4)
  - 3 new component tests (badges present, badges absent, stream-failure
    fallback) → 35/35 frontend green, `tsc` clean; devcontainer validated
    as JSONC; full backend suite re-run as a regression check (green,
    78.58%) despite no backend changes.

## Follow-ups Discovered

- Playwright e2e harness: jsdom has no WebSocket, so the component tests can
only exercise the streaming *fallback*. Proving the browser client and the Channels consumer work together end-to-end needs a real browser — this is also the missing piece flagged by the audit's "no test crosses the frontend/backend boundary" finding.
- Extend the dev container to the frontend service (or add a second
configuration) so ESLint/TypeScript tooling stops relying on a host `node_modules` the Docker-first rule also forbids.
- Surface `retrieval.jurisdiction_absent` distinctly in the coverage panel:
the backend computes it (spec 028) and the UI currently folds it into the prose note, so a jurisdictionally-lopsided result set is easy to miss.
