# Plan: HITL Quarantine Enforcement — Test Coverage & Regression Guard

> Companion to `spec.md`. Describes **how** we will satisfy the requirements.

## 1. Architecture Overview

This spec adds tests only — no production code changes. The existing dispatch
chain is confirmed correct:

```
_node_dispatch
  → force_quarantine=adapter.requires_human_approval
  → _dispatch_target(..., force_quarantine=True)
  → scout.run_and_commit(..., force_quarantine=True)
  → _quarantine() always called when force_quarantine=True
```

The plan is to intercept at each seam with `pytest-mock` and assert the
`force_quarantine=True` kwarg propagates end-to-end, plus one integration
test confirming a `PendingReview` row is written to Postgres.

## 2. Component Changes

| Layer | File / Module | Change |
|-------|---------------|--------|
| Tests | `backend/tests/autonomy/test_topic_frontier.py` | add FR-1, FR-3, FR-4 test cases |
| Tests | `backend/tests/autonomy/test_topic_frontier.py` | add FR-2 `_dispatch_target` test |

No migrations, no API changes, no frontend changes (NG1–NG3 from spec.md).

## 3. Data & Schema Migrations

None. Reads from existing `ingestionapp_pendingreview` table (integration test
only).

## 4. Tech Choices & Alternatives

- **`pytest-mock` `mocker.patch`**: keeps unit tests dependency-free and fast
  (NFR-PERF-1). Alternative (`unittest.mock.patch`) is equivalent but less
  ergonomic in pytest.
- **`@pytest.mark.django_db(transaction=True)`**: required for the integration
  test (FR-4) to avoid `SynchronousOnlyOperation` when `async_to_sync` wraps
  `_node_dispatch`. Mirrors the pattern in
  `tests/ingestion/test_scout_integration.py`.
- **`CELERY_TASK_ALWAYS_EAGER=True`**: ensures Celery tasks execute inline
  without a broker for the integration test.

## 5. Test Plan

| Test | Scope | Marker | Seam |
|------|-------|--------|------|
| `test_force_quarantine_true_passed_to_run_and_commit` | unit | `unit` | mock `scout.run_and_commit` |
| `test_dispatch_summary_shows_not_committed_when_force_quarantine` | unit | `unit` | mock `IngestionScout` |
| `test_sets_human_approval_when_adapter_requires_it` (strengthen) | unit | `unit` | existing test + new assertion |
| `test_requires_human_approval_produces_pending_review_row` | integration | `integration` | real Postgres + Celery eager |
