# Spec: Deliverable, Authenticated Agent Streaming + Real Ollama Readiness

- **ID**: 032-deliverable-agent-streaming
- **Status**: shipped
- **Owner**: @bamr87
- **Created**: 2026-08-11
- **Roadmap Epic**: continuous-evolution hardening (2026-08-10 audit)
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md) — §4 (transport events audited separately from agent calls), §8 (no unauthenticated surface when a key is configured)

## 1. Problem & Motivation

**Streaming could not deliver anything.** The WS group was keyed on the
server-generated `analysis_id`, which a client only learns from the
*response* — i.e. after the run has already finished. Worse, all three
events were emitted *after* `asyncio.gather` completed, so even a
hypothetically-subscribed client received the whole trace at once, at the
end. The consumer also accepted every connection with no authentication,
while the REST routers it shadows are key-gated.

**Ollama readiness was fictional.** The healthcheck was `ollama list`,
which succeeds the moment the server answers — with zero models installed.
`docker compose up -d ... --wait` therefore reported a healthy stack to the
nightly LegalBench job, which then ran every item against a model that did
not exist. This is not hypothetical: it happened during spec 029 work, when
a mid-pull Ollama produced ten 500s in the API suite.

The model list was also duplicated between `ollama-bootstrap.sh` and
`make local-ai-pull`, free to drift.

## 2. Goals

- G1: A client can actually receive agent events, as they happen
  (BL-20260810-06).
- G2: The WS surface is authenticated whenever the REST surface is.
- G3: Container readiness means "can serve a request", not "is listening"
  (BL-20260810-12).
- G4: One source of truth for the Ollama model set.

## 3. Non-Goals

- NG1: Reconnect/backoff and event replay — a dropped socket loses the
  in-flight trace; the REST response remains authoritative.
- NG2: Streaming *token-level* output from the LLM; these are per-agent
  step events.
- NG3: Rendering a live trace panel in Analysis Studio — the client
  primitive ships here; the UI wiring is a follow-up.

## 4. User Stories

- As a user watching an analysis, I want to see each agent finish as it
  finishes, rather than staring at a spinner until everything completes.
- As an operator, I want `--wait` to mean the model is actually loadable.

## 5. Functional Requirements

- **FR-1**: `AnalysisRequest.stream_id` — optional client-chosen id,
  validated `^[A-Za-z0-9._-]{1,64}$` at the API boundary (422 otherwise).
  Events publish to that id when supplied; otherwise the previous
  analysis-id behaviour is preserved.
- **FR-2**: Each agent's `agent_step` event is emitted **inside** the
  gather, as that agent completes — not after both finish. The event
  carries agent, analysis_id, trace_id, latency, confidence, and `degraded`.
- **FR-3**: `complete` remains the terminal event.
- **FR-4**: The consumer rejects malformed stream ids with close code
  **4400** — rejected, never sanitised, so a client cannot smuggle itself
  into another run's group.
- **FR-5**: When `AGENT_API_KEY` is configured the consumer requires it via
  `?api_key=` (browsers cannot set WebSocket handshake headers) or an
  `X-API-Key` header, closing with **4401** otherwise. With no key
  configured the socket stays open, matching the REST default-open posture.
- **FR-6**: Producer and consumer share one `stream_group()` helper so the
  group name cannot drift between them.
- **FR-7**: The Ollama healthcheck verifies the **gate model is pulled**,
  not merely that the server answers; the gate model is the first entry of
  `OLLAMA_BOOTSTRAP_MODELS`, the same value `ollama-bootstrap.sh` uses.
- **FR-8**: `OLLAMA_BOOTSTRAP_MODELS` is declared once in compose;
  `make local-ai-pull` reads it back out of the container instead of
  restating the list, and `make local-ai-verify` runs the same check.
- **FR-9**: Frontend `lib/agentStream.ts` provides `newStreamId()`,
  `agentStreamUrl()`, and `openAgentStream()`, which resolves only on
  `ready` so callers cannot post before the subscription is live.

## 6. Non-Functional Requirements

- **NFR-SEC-1**: Unauthorized sockets are closed **before** joining the
  group, so they never receive an event.
- **NFR-RESILIENCE-1**: WS emission stays fire-and-forget — a Redis outage
  cannot abort an analysis run (preserves spec 021 AC-2).
- **NFR-DX-1**: Healthcheck `start_period` accommodates a ~4 GB cold pull
  (600s) so a first boot is not marked unhealthy while it works correctly.

## 7. Data Model Impact

None.

## 8. API Surface

`POST /api/analysis` accepts optional `stream_id` (422 on a malformed
value). WS `/ws/agents/<stream_id>` gains close codes 4400 / 4401 and
optional `?api_key=`.

## 9. Agent / Crew Impact

None — the agents are unchanged; only when their step events are published.

## 10. Acceptance Criteria

- **AC-1**: Subscribing to `/ws/agents/<id>`, then posting with that
  `stream_id`, yields two `agent_step` events (one per agent) followed by
  `complete`, whose `analysis_id` matches the REST response id.
- **AC-2**: A malformed stream id is rejected at the API boundary (422) and
  at the socket (close 4400).
- **AC-3**: With `AGENT_API_KEY` set, an unauthenticated or wrong-key
  socket is closed 4401; the correct key works via query **and** header.
- **AC-4**: With no key configured, the socket connects.
- **AC-5**: The Ollama healthcheck exits 0 when the gate model is present
  and exits 1 with a diagnostic when it is not.
- **AC-6**: `newStreamId()` always matches the server's id contract;
  `openAgentStream` resolves only after `ready` and tolerates non-JSON
  frames.

## 11. LegalBench Impact

- Tasks affected: none directly. Indirectly positive: the readiness fix
  stops nightly from evaluating against a model-less Ollama, which
  previously produced spurious zero scores (now an explicit exit-2
  infrastructure error per spec 031).
- Expected delta: 0 pp.

## 12. Risks & Open Questions

- **R-1**: No reconnect/replay — a client that drops mid-run loses the
  trace and must fall back to the REST response.
- **R-2**: The API key travels in the WS query string, so it can appear in
  proxy/access logs. Acceptable for the current localhost-first posture;
  per-user tokens (BL-20260811-06) are the real fix.
- **R-3**: The stricter healthcheck lengthens first-boot time to healthy on
  a cold volume; `start_period` is set to 600s to accommodate it.

## 13. Out of Scope / Follow-ups

See `tasks.md` → `## Follow-ups Discovered` (mirrored into BACKLOG.md as
BL-20260811-13 … BL-20260811-15).
