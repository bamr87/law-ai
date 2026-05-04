# Tasks: 005-lsat-lab

- [x] **T-001** — Author `lr_bank.json` with 5 LR items (FR-1, AC-5, NFR-LICENSE-1).
- [x] **T-002** — Implement `app.lsat.bank` Pydantic models + cached loader (FR-1, NFR-PERF-1, NFR-SEC-1).
- [x] **T-003** — Implement `GET /api/lsat/questions` and mount router in `main.py` (FR-2, AC-1).
- [x] **T-004** — Implement `POST /api/lsat/grade` with audit recording (FR-3, FR-5, AC-2, AC-3, NFR-AUDIT-1).
- [x] **T-005** — Implement `GET /api/lsat/stats` aggregating audit ring (FR-4, AC-4).
- [x] **T-006** — Backend tests covering AC-1..AC-5 (NFR-COVERAGE-1).
- [x] **T-007** — Frontend `/lsat` page + `LsatLab` component + api client helpers (FR-6, AC-6).
- [x] **T-008** — Append BACKLOG follow-ups + spec validator green.

## Follow-ups Discovered

- BL-20260429-18 — LR Tutor agent.
- BL-20260429-19 — Expand bank to ≥ 50 items + CI schema check.
- BL-20260429-20 — Add Reading Comprehension + Logic Games question types.
- BL-20260503-01 — Version the LSAT tutor prompt (`prompts/lsat-tutor/v1.md`).
- BL-20260503-02 — Expand RC + LG banks to ≥10 sets each + CI passage_id check.
- BL-20260503-03 — SSE streaming variant of `POST /api/lsat/tutor`.
- BL-20260503-04 — Add LSAT Writing Sample (WS) section with rubric.
- BL-20260503-05 — Persist per-user attempt history once auth lands.
- BL-20260503-06 — Surface phoenix_trace_url + langgraph_thread_id on tutor responses.
- BL-20260503-07 — Vitest test for `used_llm=false` fallback rendering.
- BL-20260503-08 — Refresh spec to cover multi-section + concept catalog + tutor scope.
