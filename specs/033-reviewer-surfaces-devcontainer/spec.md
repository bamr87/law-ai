# Spec: Reviewer Surfaces (Live Trace, Verified Citations) + Dev Container

- **ID**: 033-reviewer-surfaces-devcontainer
- **Status**: shipped
- **Owner**: @bamr87
- **Created**: 2026-08-11
- **Roadmap Epic**: continuous-evolution hardening (2026-08-10 audit) — final medium-severity slice
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md) — §13 (unverified authority is labelled, never hidden), §1/Docker-first (editor tooling stops depending on host installs)

## 1. Problem & Motivation

Three loose ends from the audit, all about surfacing what the backend
already knows:

1. **The live trace had no consumer.** Spec 032 made agent events genuinely
   deliverable and shipped the client primitive, but Analysis Studio still
   showed an undifferentiated spinner for the whole run (BL-20260811-13).
2. **Citation verification was invisible.** Since spec 026 the backend has
   returned `verified` per source — the very flag that distinguishes an
   authority resolved against the knowledge graph from one the model
   asserted — and the UI rendered every citation identically
   (BL-20260810-02 remainder).
3. **Editor tooling contradicted Docker-first.** AGENTS.md forbids host
   `pytest`/`ruff`/`mypy`/`npm`, but Pylance and ESLint need an interpreter
   and a `node_modules` to work at all, so IntelliSense and test discovery
   were either broken or quietly violating the rule (BL-20260810-09).

## 2. Goals

- G1: Show agents completing as they complete, without making streaming a
  requirement for the analysis to succeed.
- G2: Label unverified citations in the UI rather than rendering them
  indistinguishably from verified ones (§13).
- G3: Give the editor a first-class environment that *is* the container the
  Makefile and CI use.

## 3. Non-Goals

- NG1: Reconnect / event replay (BL-20260811-14).
- NG2: Streaming the LSAT tutor or autonomy cycles (BL-20260811-15).
- NG3: A frontend dev container — the backend service is where the
  host-toolchain conflict actually bites.

## 4. User Stories

- As a user, I want to see which agent has finished while I wait, so a slow
  run is legible rather than opaque.
- As a reviewer, I want unresolved citations visibly flagged, so I check
  them instead of trusting them.
- As a contributor, I want IntelliSense and test discovery without
  installing Python or Node on my host.

## 5. Functional Requirements

- **FR-1**: Analysis Studio generates a `stream_id`, subscribes via
  `openAgentStream`, and only then POSTs — the ordering spec 032 requires.
- **FR-2**: Each `agent_step` renders immediately in a `LiveTrace` panel
  (agent name, latency, and a `degraded` marker when no engine ran).
- **FR-3**: Streaming is strictly an enhancement: if the socket fails to
  open, the request proceeds **without** `stream_id` and the REST response
  remains authoritative. The live panel renders nothing rather than showing
  an empty "live" box that never fills.
- **FR-4**: The socket is closed in `finally`, so neither success nor
  failure leaks a connection.
- **FR-5**: Sources render a `verified in graph` badge when
  `verified === true` and an `unverified` badge (with an explanatory
  tooltip) when `verified === false`; when the field is absent — an older
  path that never ran the check — no badge is shown rather than guessing.
- **FR-6**: `.devcontainer/devcontainer.json` attaches VS Code to the
  existing compose `backend` service with `overrideCommand` (so daphne does
  not own the container lifecycle), the sanctioned extension set, pytest
  discovery enabled, and `PHOENIX_COLLECTOR_ENDPOINT=""` so in-editor test
  runs never hit the tracing collector.

## 6. Non-Functional Requirements

- **NFR-A11Y-1**: The live panel is an `aria-live="polite"` labelled region,
  so steps are announced without stealing focus.
- **NFR-RESILIENCE-1**: No streaming failure mode can prevent an analysis
  from completing.

## 7. Data Model Impact

None.

## 8. API Surface

None — consumes the `stream_id` and `verified` fields shipped by specs
032 and 026.

## 9. Agent / Crew Impact

None.

## 10. Acceptance Criteria

- **AC-1**: With verification reported, both a `verified in graph` and an
  `unverified` badge render, and the unresolved citation is still listed.
- **AC-2**: With no `verified` field, neither badge renders.
- **AC-3**: When the stream cannot connect, the analysis still completes and
  no live panel is rendered.
- **AC-4**: `devcontainer.json` is valid JSONC targeting the compose
  `backend` service at `/app`.

## 11. LegalBench Impact

- Tasks affected: none (presentation and tooling only).
- Expected delta: 0 pp.

## 12. Risks & Open Questions

- **R-1**: jsdom has no WebSocket, so component tests exercise the
  *fallback* path. The streaming path is covered by the backend end-to-end
  test (spec 032) plus the `lib/agentStream` unit tests; a browser-level
  test of the two together needs the Playwright e2e harness that does not
  exist yet.
- **R-2**: A `verified` badge reflects resolution against *our* corpus, not
  correctness of the proposition — the tooltip says so explicitly to avoid
  the §13 "authority ≠ correctness" trap.

## 13. Out of Scope / Follow-ups

See `tasks.md` → `## Follow-ups Discovered` (mirrored into BACKLOG.md as
BL-20260811-16 … BL-20260811-18).
