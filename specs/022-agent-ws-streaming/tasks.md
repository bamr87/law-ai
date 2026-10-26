# Tasks: Agent WebSocket Streaming — Live Progress from LegalAnalyst & PrecedentHunter

> Each task must reference one or more `FR-*` / `NFR-*` / `AC-*` IDs from `spec.md`.
> CI's `spec_validator.py` enforces that every
> requirement in `spec.md` is referenced by at least one task.

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: `@copilot`.
- Each task lists exact files to touch and how to verify.

---

## T-001 — Resolve OQ-1: async channel layer call pattern

- **Refs**: FR-1, FR-2, FR-3
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/analysis/urls.py` (read; determine async vs sync path)
- **Steps**:
  1. Inspect the actual dispatch path of `_run_analysis`:
     `AnalysisView.post` → `async_to_sync(_run_analysis)` or direct ASGI async call?
  2. Confirm `_run_analysis` is `async def` (it is — see `urls.py:30`) and is
     awaited within a running event loop provided by Daphne.
  3. Conclude: use `await layer.group_send(group, event)` directly inside
     `_run_analysis`. Document in a code comment.
- **Verify**: Code review; no runtime test needed for this task alone.

## T-002 — Add `_emit_ws_event` helper and wire into `_run_analysis`

- **Refs**: FR-1, FR-2, FR-3, FR-4, FR-5, NFR-PERF-1, NFR-AUDIT-1, NFR-SEC-1, NFR-BACK-COMPAT-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/analysis/urls.py` (edit)
- **Steps**:
  1. Add `async def _emit_ws_event(analysis_id: str, payload: dict[str, object]) -> None:`
     that calls `await layer.group_send(f"agent-run-{analysis_id}", {"type": "agent_event", "payload": payload})`
     and wraps in `try/except Exception` with `logger.warning` on failure (FR-1).
  2. After `irac = await ...LegalAnalyst...` completes, call
     `await _emit_ws_event(analysis_id, {"type": "agent_step", "agent": "LegalAnalyst",
     "trace_id": irac.trace_id, "latency_ms": ..., "confidence": irac.confidence})` (FR-2).
  3. After `precedents = await ...PrecedentHunter...` completes, emit `agent_step:PrecedentHunter` (FR-2).
  4. After both complete, emit `{"type": "complete", "analysis_id": analysis_id,
     "confidence": confidence, "requires_human_review": requires_human_review}` (FR-3).
  5. Log each emit via `provenance.log_agent_call` or equivalent with `event_type="ws_event_sent"` (FR-4).
  6. `AnalysisResponse` schema is unchanged — no new fields added (NFR-BACK-COMPAT-1).
- **Verify**:
  - `docker compose run --rm backend pytest tests/api/test_analysis.py -q`
  - `make lint` exits 0

## T-003 — Add unit test `test_agent_ws_events_emitted`

- **Refs**: FR-6, AC-1, AC-2, AC-3, AC-5
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/tests/api/test_analysis.py` (edit)
- **Steps**:
  1. Add `test_agent_ws_events_emitted` that patches `channels.layers.get_channel_layer`
     with an `AsyncMock` channel layer mock.
  2. POST to `/api/analysis` with valid text.
  3. Assert `mock_layer.group_send` was called exactly 3× (AC-1).
  4. Assert call #1 payload has `type="agent_step"` and `agent="LegalAnalyst"`.
  5. Assert call #2 payload has `type="agent_step"` and `agent="PrecedentHunter"`.
  6. Assert call #3 payload has `type="complete"` and `analysis_id` set.
  7. Assert HTTP response is 200 with unchanged schema (AC-3).
  8. Add `test_agent_ws_events_resilient_to_channel_layer_failure`:
     patch `get_channel_layer` to raise; assert POST still returns 200 (AC-2).
- **Verify**:
  - `docker compose run --rm backend pytest tests/api/test_analysis.py -q` — both new tests pass

## T-004 — Verify consumer test still passes (AC-4)

- **Refs**: FR-7, AC-4
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/tests/agentsapi/test_consumer.py` (read-only; must not be changed)
- **Steps**:
  1. Run `docker compose run --rm backend pytest tests/agentsapi/test_consumer.py -q`.
  2. Confirm `test_agent_run_consumer_ready_and_group_event` still passes after T-002 changes.
- **Verify**: Test output shows 1 passed, 0 failed.

## T-005 — Lint, coverage, and full gate run (AC-5, AC-6)

- **Refs**: AC-5, AC-6, NFR-PERF-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - (no file changes; gate run only)
- **Steps**:
  1. `make lint` — must exit 0.
  2. `make test-backend` — must exit 0 with ≥ 75 % coverage (`--cov-fail-under=75`).
  3. `make typecheck` — mypy --strict must exit 0.
  4. `python3 scripts/spec_validator.py` — all specs pass.
  5. `python3 scripts/backlog_lint.py` — PASS.
- **Verify**: All commands above exit 0.

## T-006 — Update BACKLOG.md: move BL-20260503-09 → Done, resolve BL-20260429-24

- **Refs**: AC-1 (indirectly — constitutes the shipped item)
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `BACKLOG.md` (edit)
- **Steps**:
  1. Move `BL-20260503-09` from `## Open` to `## Done` with resolution note.
  2. Move `BL-20260429-24` from `## Open` to `## Done` (partially resolved: WS half done; SSE follow-up filed).
  3. Run `python3 scripts/backlog_lint.py` — must pass.
- **Verify**: `python3 scripts/backlog_lint.py` exits 0.

---

## Follow-ups Discovered

> Append-only. Mirror each item into [BACKLOG.md](../../BACKLOG.md) with a `BL-YYYYMMDD-NN` id.

- **BL-20260602-05** — *feature, low* — Sequential agent execution mode (opt-in flag) for `_run_analysis` so events stream progressively in real-time instead of arriving together after `asyncio.gather`. Current implementation emits all three events after both agents finish. _Surfaced in:_ specs/022-agent-ws-streaming.
- **BL-20260602-06** — *feature, low* — Frontend progress bar wired to `/ws/agents/{analysis_id}` events: render a live step-by-step trace in the Analysis Studio UI when `agent_step` events arrive. _Surfaced in:_ specs/022-agent-ws-streaming.
