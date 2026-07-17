# Spec: HITL Quarantine Enforcement — Test Coverage & Regression Guard

- **ID**: 023-hitl-quarantine-enforcement
- **Status**: shipped
- **Owner**: @copilot
- **Created**: 2026-06-02
- **Roadmap Epic**: BACKLOG BL-20260511-30
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md) §3, §5, §6

## 1. Problem & Motivation

Constitution §5 and `specs/018` NFR-HITL-1 require that when any `SourceAdapter.requires_human_approval` is `True`, **every** `RawDoc` it produces MUST route through `PendingReview` (quarantine) regardless of confidence score. This prevents high-stakes or new-source documents from being committed directly to Neo4j without a human reviewer.

The production code is **already wired correctly**:

```
_node_dispatch
  → force_quarantine=adapter.requires_human_approval
  → _dispatch_target(..., force_quarantine=True)
  → scout.run_and_commit(..., force_quarantine=True)
  → _quarantine() always called when force_quarantine=True
```

However, the only existing test (`test_sets_human_approval_when_adapter_requires_it`) checks only that `state["human_approval_required"] is True`. It never asserts that `scout.run_and_commit` was actually called with `force_quarantine=True`, and its mock returns `{"committed": True}` — the wrong value for a quarantined doc. A regression (e.g. accidental removal of `force_quarantine=` kwarg in `_dispatch_target`) would pass silently.

This spec adds the safety-net tests that make the HITL enforcement verifiable and regression-proof, closing BL-20260511-30.

## 2. Goals

- **G1**: Add a unit test asserting `run_and_commit` is called with
  `force_quarantine=True` when the adapter has `requires_human_approval=True`.
- **G2**: Add a unit test asserting the dispatch summary records `committed: False`
  (quarantined) when `force_quarantine=True` reaches the real `IngestionScout`.
- **G3**: Add an `@pytest.mark.integration` test confirming that a
`requires_human_approval=True` adapter produces a `PendingReview` row (not a Neo4j `Case` node) after a full `_node_dispatch` call against a live stack.
- **G4**: Strengthen `test_sets_human_approval_when_adapter_requires_it` to
  also assert `run_and_commit.call_args` includes `force_quarantine=True`.

## 3. Non-Goals

- **NG1**: Changes to production code in `topic_frontier.py` or `scout.py`
  (implementation is confirmed correct; only tests are added).
- **NG2**: Adding new adapters or changing `requires_human_approval` values on
  existing adapters (all three current adapters have `requires_human_approval=False`).
- **NG3**: Frontend UI changes.

## 4. User Stories

- As a **legal reviewer**, I want confidence that documents from
`requires_human_approval=True` sources always land in the HITL queue, so that no unreviewed ingestion bypasses the approval gate.
- As a **developer**, I want CI tests that catch any accidental removal of
`force_quarantine=True` in the dispatch chain, so that HITL regressions are surfaced immediately.

## 5. Functional Requirements

- **FR-1**: A unit test `test_force_quarantine_true_passed_to_run_and_commit`
calls `_node_dispatch` with an adapter whose `requires_human_approval=True`, captures the mock `scout.run_and_commit` call args, and asserts `call_kwargs["force_quarantine"] is True`.
- **FR-2**: A unit test `test_dispatch_summary_shows_not_committed_when_force_quarantine`
calls `_dispatch_target` with `force_quarantine=True` and a mocked `IngestionScout` whose `run_and_commit` returns `{"committed": False, "pending": True, "confidence": 0.5}`, and asserts the resulting dispatch entry has `committed=False`.
- **FR-3**: Strengthen the existing `test_sets_human_approval_when_adapter_requires_it`
  by adding `scout.run_and_commit.assert_called_once_with(ANY, force_quarantine=True)`.
- **FR-4**: An `@pytest.mark.integration` test
  `test_requires_human_approval_produces_pending_review_row` that:
  1. Creates an in-memory adapter stub with `requires_human_approval=True`
     returning one `RawDoc`.
  2. Calls `_node_dispatch` with a real `IngestionScout` using
     `CELERY_TASK_ALWAYS_EAGER=True` and `@pytest.mark.django_db(transaction=True)`.
  3. Asserts a `PendingReview` row exists in Postgres for the dispatched doc's
     `source_url` (via `PendingReview.objects.filter(source=...)`).
  4. Asserts the dispatch result entry has `committed=False`.

## 6. Non-Functional Requirements

- **NFR-PERF-1**: All unit tests (FR-1 to FR-3) complete in < 1 s each (no
  network calls, Celery eager).
- **NFR-AUDIT-1**: No changes to `core.provenance` logging; existing provenance
  coverage is sufficient.
- **NFR-HITL-1**: This spec exists to enforce §5 compliance — it must not
  introduce any code change that weakens the HITL gate.
- **NFR-COV-1**: Backend line coverage on `topic_frontier.py` and `scout.py`
  must not decrease.

## 7. Data Model Impact

No new Neo4j nodes, Postgres tables, or vector collections. The integration test reads from the existing `ingestionapp_pendingreview` table.

Reference: [docs/data-model.md](../../docs/data-model.md) — `PendingReview` model (`law_ai.ingestionapp.models`).

## 8. API Surface

No new or changed API routes.

## 9. Agent / Crew Impact

No new agents. Touches test files only:

- **TopicFrontier** (`backend/law_ai/agents_runtime/graphs/topic_frontier.py`) —
  test-only; production code is unchanged.
- **IngestionScout** (`backend/law_ai/ingestionapp/services/scout.py`) —
  test-only; confirms `force_quarantine` path is exercised.

## 10. Acceptance Criteria

- **AC-1**: Given an adapter with `requires_human_approval=True`, when
`_node_dispatch` is called, then `scout.run_and_commit` is called with `force_quarantine=True` (verified via `assert_called_once_with`).
- **AC-2**: Given `force_quarantine=True`, when `_dispatch_target` returns a
  dispatch entry, then `entry["committed"] is False`.
- **AC-3**: (Integration) Given a live Postgres + `CELERY_TASK_ALWAYS_EAGER=True`
and an adapter with `requires_human_approval=True`, when `_node_dispatch` executes, then a `PendingReview` row exists with the dispatched doc's `source_url` and `committed=False` in the dispatch summary.
- **AC-4**: `make test-backend` exits 0 and backend coverage does not decrease.
- **AC-5**: `make lint` exits 0 (ruff + black).

## 11. LegalBench Impact

- No reasoning logic changed; LegalBench regression run not required.
- Expected delta: 0 pp on all tasks.

## 12. Risks & Open Questions

- **R-1**: The integration test (FR-4) requires `CELERY_TASK_ALWAYS_EAGER=True`
and Django ORM access in an async test context. Use `@pytest.mark.django_db(transaction=True)` and wrap the async dispatch call in `asyncio.run` or `asgiref.sync.async_to_sync` from a **sync** test body to avoid `SynchronousOnlyOperation` (mirrors fix from BL-20260510-01 / `tests/ingestion/test_scout_integration.py`).

No open questions — spec is self-contained and implementation is confirmed correct.

## 13. Out of Scope / Follow-ups

- BL-20260511-31 — Migrating `TopicFrontier` to a proper `StateGraph` (separate
  spec; does not affect HITL enforcement).
- BL-20260510-01 — Full Celery/Django-ORM integration path for `PendingReview`
  (broader than this spec; this spec only adds the HITL-path verification test).

## Origin & Background

Claimed from: **BL-20260511-30** (feature, high) — "Enforce `requires_human_approval=True` quarantine path in `TopicFrontier._node_dispatch`". Surfaced during specs/018-autonomous-framework PR review.
