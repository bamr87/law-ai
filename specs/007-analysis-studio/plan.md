# Plan: 007 — Analysis Studio

## Approach

Three layers, fully testable in isolation:

1. **Crew tweaks** — `LegalAnalyst` and `PrecedentHunter` get an
optional `trace_id` field on their output models (FR-6). Their `run` methods capture the trace_id returned by `provenance.log_agent_call` and stamp it on the output before returning.
2. **Hardened API** — `app/api/analysis.py` rewritten:
   - Pydantic-validated request (FR-1, NFR-SEC-1).
   - `asyncio.gather` parallel run (FR-2, NFR-PERF-1).
   - Top-level `analysis_id`, mean confidence, HITL flag, umbrella `analysis_run` audit event (FR-3, FR-4, FR-5, NFR-HITL-1).
3. **UI** — `app/analysis/page.tsx` server shell + client
`components/AnalysisStudio.tsx`. Reuses the existing `AgentTrace` component for the trace panel. MSW-tested.

## File Layout

```
backend/app/api/analysis.py              (rewrite)
backend/app/agents/crews/legal_analyst.py     (edit — trace_id on output)
backend/app/agents/crews/precedent_hunter.py  (edit — trace_id on output)
backend/tests/api/test_analysis.py        (new)

frontend/app/analysis/page.tsx           (new — server shell)
frontend/components/AnalysisStudio.tsx   (new — client)
frontend/lib/api.ts                      (edit — runAnalysis + types)
frontend/__tests__/components/AnalysisStudio.test.tsx (new — MSW)
```

## Why These Choices

- **Parallel via `asyncio.gather`**: zero new infra, halves wall-clock latency for the common case where both agents run independently.
- **Single umbrella audit event**: lets the future drill-down view
(BL-20260429-14) stitch `LegalAnalyst` + `PrecedentHunter` into one "analysis" record without a relational schema. Carries `child_trace_ids` so the link is explicit (R-1).
- **`requires_human_review` derived purely from confidence**: keeps the
HITL gate testable and predictable; threshold (0.7) matches the ingestion pipeline (spec 001) for consistency.
- **Reuse `AgentTrace` component**: the spec 003 component already renders steps + confidence — extending it would have been overkill.

## Cross-Cutting Concerns

- **Provenance**: every existing call site keeps logging; the new
umbrella event piggybacks on `provenance.log_agent_call` so no new serialiser is needed.
- **HITL**: response carries `requires_human_review`; the UI surfaces
it as an amber banner. Does not block the response — review is the caller's choice.
- **Tests**: ≥ 75% backend / ≥ 70% frontend. New API has ~6 tests, component has 3 (rendering + sample loader + HITL banner).

## Risk Mitigations

- **R-1 (trace ID confusion)**: umbrella event includes
`child_trace_ids` so the relationship is queryable. Documented in audit-store consumers.
- **R-2 (huge payload)**: hard cap `len(text) ≤ 20_000` enforced by Pydantic + UI counter showing remaining characters.

## Out-of-Scope (Tracked as Follow-ups)

- Streaming SSE response, save/share, real GraphRAG, drill-down view.
