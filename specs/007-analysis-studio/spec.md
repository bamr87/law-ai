# Spec: Analysis Studio

- **ID**: 007-analysis-studio
- **Status**: shipped
- **Owner**: @copilot
- **Created**: 2026-04-29
- **Roadmap Epic**: User request 2026-04-29 — "build the analysis studio"
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md) §§1–11.

## 1. Problem & Motivation

The home page advertises the Analysis Studio at `/analysis`, but the route
404s. The `/api/analysis` endpoint exists as a thin stub that runs
`LegalAnalyst` + `PrecedentHunter` sequentially, returns mock data, and
synthesises a fake `id`/`timestamp`. There is:

- no input validation (empty `text` is accepted; no max length),
- no parallelism (analyst + hunter run serially),
- no HITL flag despite the constitution mandating one for high-stakes
  outputs (constitution §1, §11),
- no `trace_id` exposed to the UI so audit drill-down is impossible,
- no UI at all.

This blocks the "multi-agent legal analysis with traces, IRAC briefs, and
precedents" pillar advertised on the home page.

## 2. Goals

- G1: Harden `POST /api/analysis` with input validation, parallel agent
  execution, returned `trace_id`s, and a confidence-driven HITL flag.
- G2: Ship `/analysis` page with a textarea, jurisdiction selector,
  sample loader, IRAC card, precedents list, agent trace, and HITL banner.
- G3: Every analysis run lands a `provenance.log_agent_call` event per
  agent and a single `analysis_run` event tying both `trace_id`s together.
- G4: Reuse the existing `AgentTrace` and `provenance` infra — no new
  dependencies.

## 3. Non-Goals

- NG1: Real GraphRAG / LLM integration. The `LegalAnalyst` and
  `PrecedentHunter` keep their mock outputs (closing those TODOs is
  tracked separately as BL-20260430-03 and BL-20260430-04).
- NG2: Authn/z (same posture as specs 003, 006).
- NG3: Streaming responses (SSE / WebSocket). Single JSON response is
  sufficient for MVP.
- NG4: Persisting full request text — only hashed in audit log
  (privacy-preserving, matches existing provenance behaviour).

## 4. User Stories

- As a **lawyer**, I want to paste a fact pattern and get an IRAC brief
  with cited precedents in one click so I can iterate on a memo without
  context-switching.
- As a **reviewer**, I want every analysis to expose a `trace_id` so I
  can find the run on the Agent Ops dashboard.
- As a **maintainer**, I want low-confidence analyses to surface a HITL
  banner so we never silently ship hallucinated legal advice.

## 5. Functional Requirements

- **FR-1**: `POST /api/analysis` body validates with Pydantic:
  `text` (1 ≤ len ≤ 20_000), `jurisdiction` (optional, ≤ 64 chars),
  `case_id` (optional, ≤ 200 chars).
- **FR-2**: `LegalAnalyst.run(...)` and `PrecedentHunter.run(...)` are
  invoked **in parallel** via `asyncio.gather` and the wall-clock latency
  is measured.
- **FR-3**: Both crew classes return their `trace_id` in the response.
  The route generates a top-level `analysis_id` (`an-` + 12 hex chars)
  and overall `confidence` = mean of the two agent confidences.
- **FR-4**: Response model `AnalysisResponse`:
  ```
  {
    "id": str,
    "timestamp": iso8601,
    "latency_ms": int,
    "confidence": float,
    "requires_human_review": bool,    # true when confidence < 0.7
    "irac": IRACOutput,
    "precedents": PrecedentList,
    "agent_trace": [
      {"agent": "LegalAnalyst",   "trace_id": str, "latency_ms": float, "confidence": float},
      {"agent": "PrecedentHunter","trace_id": str, "latency_ms": float, "confidence": float}
    ]
  }
  ```
- **FR-5**: After both agents return, the route records an
  `analysis_run` event via `provenance.log_agent_call` (agent_name=
  `"AnalysisStudio"`, sources merged from both agents).
- **FR-6**: `LegalAnalyst.run` and `PrecedentHunter.run` are updated to
  also return their generated `trace_id` so the route can surface it
  without re-hashing — exposed as `IRACOutput.trace_id` and
  `PrecedentList.trace_id` (Optional[str], default None for back-compat).
- **FR-7**: Frontend `app/analysis/page.tsx` server shell + new
  `components/AnalysisStudio.tsx` client component:
  - Textarea + jurisdiction `<select>` (US, US-CA, US-NY, EU, Other).
  - "Load sample" button populates a canned negligence fact pattern.
  - Submit → spinner → results: IRAC card (Issue / Rule / Application /
    Conclusion), Precedents list with relevance bars, `AgentTrace`
    component reused from spec 003.
  - Amber HITL banner when `requires_human_review: true`.
  - `trace_id` and `analysis_id` shown in a footer chip with copy
    affordance.
- **FR-8**: `lib/api.ts` gains a typed `runAnalysis(input)` client
  returning the full `AnalysisResponse`.

## 6. Non-Functional Requirements

- **NFR-PERF-1**: With mock agents, end-to-end p95 < 200 ms (parallel
  `asyncio.gather` keeps wall-clock close to `max(latency)`, not sum).
- **NFR-AUDIT-1**: Three audit events per request — `LegalAnalyst`,
  `PrecedentHunter`, `AnalysisStudio` (the umbrella). Verified by reading
  `audit_store.tail`.
- **NFR-HITL-1**: Every response sets `requires_human_review` purely as a
  function of `confidence` (< 0.7 → true). Documented in the OpenAPI
  schema via Pydantic field description.
- **NFR-SEC-1**: Pydantic validation rejects empty / over-long input
  (FR-1). The raw `text` is never re-emitted in audit events — only its
  `hash()` per the existing `provenance.log_agent_call` contract.
- **NFR-COVERAGE-1**: Backend coverage stays ≥ 75% repo-wide; new code
  ≥ 85%. Frontend coverage stays ≥ 70%.

## 7. Data Model Impact

- No Neo4j schema change.
- `IRACOutput` and `PrecedentList` gain optional `trace_id: str | None`
  field for FR-6.

## 8. API Surface

```
POST /api/analysis
  request:  AnalysisRequest { text, jurisdiction?, case_id? }
  response: AnalysisResponse (see FR-4)
```

## 9. Agent / Crew Impact

- `LegalAnalyst.run` and `PrecedentHunter.run` updated to return
  `trace_id` on their structured output (FR-6). No prompt / behavioural
  change. Mock outputs retained (NG1).
- New "AnalysisStudio" umbrella entry in audit log (FR-5) — not a
  registered crew, just a provenance label.

## 10. Acceptance Criteria

- **AC-1**: `POST /api/analysis` with `{"text": "..."}` returns HTTP 200
  with all FR-4 fields populated and `len(agent_trace) == 2` (verifies
  FR-1, FR-2, FR-3, FR-4).
- **AC-2**: `POST /api/analysis` with `{"text": ""}` returns HTTP 422
  (verifies FR-1).
- **AC-3**: After one successful run, `audit_store.tail(10)` contains
  exactly three events whose `agent` ∈ {LegalAnalyst, PrecedentHunter,
  AnalysisStudio} (verifies FR-5, NFR-AUDIT-1).
- **AC-4**: When both agents return `confidence ≥ 0.7`,
  `requires_human_review == false`. When monkeypatched so one agent
  returns `confidence = 0.4`, the response sets
  `requires_human_review == true` (verifies FR-3, NFR-HITL-1).
- **AC-5**: Wall-clock latency of a request where each mocked agent
  sleeps 50 ms is < 90 ms (verifies FR-2 parallelism — serial would be
  ≥ 100 ms).
- **AC-6**: Frontend `/analysis` renders the IRAC card, the precedents
  list, and the agent trace from MSW-mocked API; clicking "Load sample"
  populates the textarea; the HITL banner appears when the mock returns
  `requires_human_review: true` (verifies FR-7).

## 11. LegalBench Impact

- Tasks affected: none (mock agents).
- Expected delta: 0 pp. Real reasoning lands when BL-20260430-03 and -04
  are implemented; this spec ships the rails.

## 12. Risks & Open Questions

- **R-1**: Returning two `trace_id`s plus an umbrella one could confuse
  the audit drill-down (BL-20260429-14). Mitigation: the umbrella event
  carries `child_trace_ids: [..]` so the relationship is explicit.
- **R-2**: A 20 KB textarea could OOM under load. Mitigation: hard cap
  in Pydantic; document the limit in the UI.

## 13. Out of Scope / Follow-ups

- Streaming agent output (SSE).
- Saving / sharing analyses.
- Real LegalAnalyst + PrecedentHunter (BL-20260430-03/04).
- Drill-down view (BL-20260429-14).
