# Spec: Agent WebSocket Streaming — Live Progress from LegalAnalyst & PrecedentHunter

- **ID**: 022-agent-ws-streaming
- **Status**: shipped
- **Owner**: @copilot
- **Created**: 2026-06-02
- **Roadmap Epic**: BL-20260503-09 / BL-20260429-24
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md) §2, §4, §5

## 1. Problem & Motivation

`POST /api/analysis` currently blocks until both `LegalAnalyst` and `PrecedentHunter` complete (~1–5 s on local Ollama), then returns one JSON blob. There is no progress feedback — users see a spinner and cannot tell which stage the pipeline is on.

The `AgentRunConsumer` WebSocket skeleton was shipped in spec-011 T-010: it accepts connections at `/ws/agents/{run_id}`, joins Redis channel group `agent-run-{run_id}`, and forwards any `agent_event` group messages to the client. Currently no producers emit events to those groups — the consumer is a skeleton waiting for traffic.

This spec wires the producers: `_run_analysis` in `law_ai/analysis/urls.py` publishes `agent_step` events to the channel group after each agent completes, so a client connected to `/ws/agents/{analysis_id}` sees real-time step progress and a final `complete` event, while the HTTP response stays unchanged (backward compatible).

## 2. Origin & Background

- **BL-20260503-09** — *feature, med* — "Real Channels producers for
`/ws/agents/{run_id}` so `LegalAnalyst`/`PrecedentHunter` progress streams to the consumer skeleton landed by spec 011 T-010." _Surfaced in:_ specs/011-django-backend.
- **BL-20260429-24** — *feature, med* — "Stream agent trace events to the
`/analysis` UI via SSE so users see `LegalAnalyst` → `PrecedentHunter` progress." _Surfaced in:_ specs/007-analysis-studio. This spec resolves the WS half; SSE remains a follow-up.

## 3. Goals

- **G1**: Emit a `{"type":"agent_step","agent":"LegalAnalyst",...}` event
  to `agent-run-{analysis_id}` after `LegalAnalyst.run()` returns.
- **G2**: Emit a `{"type":"agent_step","agent":"PrecedentHunter",...}`
  event after `PrecedentHunter.run()` returns.
- **G3**: Emit a `{"type":"complete","analysis_id":...}` event when the
  full pipeline finishes (before the HTTP response returns).
- **G4**: Keep `POST /api/analysis` response schema and semantics
  unchanged (backward compatible; no new required fields).
- **G5**: Wire the `analysis_id` (already in `AnalysisResponse.id`) as the
  channel group key so clients can subscribe before calling POST.

## 4. Non-Goals

- **NG1**: Moving analysis to a Celery background task (HTTP still blocks;
  async job queue is a future spec).
- **NG2**: Streaming individual tokens from Ollama (token-level streaming
  requires a separate effort to stream Ollama output).
- **NG3**: Frontend changes — existing `AgentDashboard` already polls
  `/api/agents/runs`; real-time WebSocket UI is a follow-up.
- **NG4**: Auth on WebSocket connections (tracked in BL-20260430-09).
- **NG5**: SSE variant of the stream endpoint (tracked as
  BL-20260429-24 follow-up).

## 5. Functional Requirements

- **FR-1**: `_run_analysis` calls
`channel_layer.group_send(f"agent-run-{analysis_id}", event)` after each agent step using `async_to_sync` or native async call, depending on whether `_run_analysis` is async. Events are fire-and-forget; if the channel layer is unavailable, the error is logged but does NOT abort the analysis.
- **FR-2**: The `agent_step` event payload carries:
  `{"type":"agent_event","payload":{"type":"agent_step","agent":<name>,
  "trace_id":<str|null>,"latency_ms":<float>,"confidence":<float>}}`.
The outer `type: "agent_event"` key is required by Channels to route to `AgentRunConsumer.agent_event()`.
- **FR-3**: After both agents finish, emit a `complete` event:
`{"type":"agent_event","payload":{"type":"complete","analysis_id":<id>, "confidence":<float>,"requires_human_review":<bool>}}`.
- **FR-4**: Every `group_send` call is logged via `core.provenance`
  (event type `ws_event_sent`; `source=analysis`; `confidence=1.0`).
- **FR-5**: If no subscriber is connected (empty group), the `group_send`
is still called (Channels silently drops it) — no special handling needed.
- **FR-6**: A unit test in `tests/api/test_analysis.py` patches the
channel layer and asserts the correct sequence of `group_send` calls (two `agent_step` + one `complete`).
- **FR-7**: The existing `test_agent_run_consumer_ready_and_group_event`
integration test in `tests/agentsapi/test_consumer.py` must still pass (no consumer changes).

## 6. Non-Functional Requirements

- **NFR-PERF-1**: Each `group_send` adds ≤ 5 ms overhead to the total
  response latency (Redis call; negligible vs Ollama latency).
- **NFR-AUDIT-1**: Every `group_send` call logged via `core.provenance`
  per FR-4.
- **NFR-SEC-1**: `group_send` payloads contain no PII beyond what the HTTP
  response already returns (trace IDs, latency, confidence).
- **NFR-BACK-COMPAT-1**: `AnalysisResponse` schema unchanged; `analysis_id`
  is already present as `id`. No new required fields.

## 7. Data Model Impact

No Neo4j or Postgres changes. Redis channel-group messages are ephemeral.

Reference: [docs/data-model.md](../../docs/data-model.md) — no changes.

## 8. API Surface

**Unchanged HTTP route**: `POST /api/analysis` — request/response schema identical to spec-007/spec-011 definition. The `id` field in the response is already the `analysis_id` that clients should use as the WS channel key.

**Existing WebSocket route** (no change to routing or consumer): `/ws/agents/{run_id}` — `AgentRunConsumer`. Clients now receive the following new events during an active analysis:

| Event `type` in payload | When emitted | Key fields |
|---|---|---|
| `agent_step` | After each agent completes | `agent`, `trace_id`, `latency_ms`, `confidence` |
| `complete` | After both agents finish | `analysis_id`, `confidence`, `requires_human_review` |

## 9. Agent / Crew Impact

No new agents. Changes to `law_ai/analysis/urls.py` (`_run_analysis` function) to call the channel layer. See [docs/agent-roles.md](../../docs/agent-roles.md) for `LegalAnalyst` and `PrecedentHunter` — their `run()` signatures are unchanged.

## 10. Acceptance Criteria

- **AC-1**: Given a client subscribed to `/ws/agents/{analysis_id}` before
the POST completes, when `POST /api/analysis` is called, then the client receives an `agent_step` event for `LegalAnalyst`, an `agent_step` event for `PrecedentHunter`, and a `complete` event — in that order.
- **AC-2**: Given the channel layer is unavailable (e.g. Redis down), when
`POST /api/analysis` is called, then the HTTP response is returned normally (no 500 error); an error is logged but the analysis result is not affected.
- **AC-3**: The `AnalysisResponse` JSON returned by POST is identical to
  the pre-spec schema (no new required fields, no field removals).
- **AC-4**: `test_agent_run_consumer_ready_and_group_event` still passes.
- **AC-5**: `make test-backend` exits 0; coverage on `analysis/urls.py`
  does not decrease.
- **AC-6**: `make lint` exits 0.

## 11. LegalBench Impact

- No reasoning changes to `LegalAnalyst` or `PrecedentHunter`.
- Expected delta: 0 pp on all tasks.

## 12. Risks & Open Questions

**OQ-1 (RESOLVED)** — `_run_analysis` is `async def` and is dispatched via `asgiref.sync.async_to_sync` into Daphne's existing ASGI event loop. Calling `await layer.group_send(...)` directly inside `_run_analysis` is correct and non-blocking. No deadlock risk. Implemented in `backend/law_ai/analysis/urls.py` (`_emit_ws_event` helper).

## 13. Out of Scope / Follow-ups

- SSE streaming variant of `/api/analysis` (BL-20260429-24 partial — SSE
  not covered here).
- Moving analysis to a Celery background task for truly async POST
  (BL-20260429-25).
- WebSocket auth / API-key gating on the WS consumer (BL-20260430-09).
- Frontend real-time progress bar wired to the WS events (BL-20260502-05).
