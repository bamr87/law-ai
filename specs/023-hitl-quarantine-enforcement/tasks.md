# Tasks: HITL Quarantine Enforcement — Test Coverage & Regression Guard

> Each task must reference one or more `FR-*` / `NFR-*` / `AC-*` IDs from `spec.md`. CI's [spec_validator.py](../../scripts/spec_validator.py) enforces that every requirement in `spec.md` is referenced by at least one task.

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: GitHub handle or `@copilot` / `@agent:<role>`.

---

## T-001 — Add unit test: force_quarantine=True propagates to run_and_commit

- **Refs**: FR-1, AC-1, NFR-PERF-1, NFR-HITL-1
- **Owner**: @copilot
- **Status**: `[ ]`
- **Files**:
  - `backend/tests/autonomy/test_topic_frontier.py`
- **Steps**:
  1. Create an adapter stub with `requires_human_approval=True`.
  2. Patch `scout.run_and_commit` with `mocker.patch`.
  3. Call `_node_dispatch` and capture `call_args`.
  4. Assert `call_kwargs["force_quarantine"] is True`.
- **Verify**: `pytest tests/autonomy/test_topic_frontier.py::test_force_quarantine_true_passed_to_run_and_commit -q` passes in < 1 s.

## T-002 — Add unit test: dispatch summary records committed=False when force_quarantine=True

- **Refs**: FR-2, AC-2, NFR-PERF-1
- **Owner**: @copilot
- **Status**: `[ ]`
- **Files**:
  - `backend/tests/autonomy/test_topic_frontier.py`
- **Steps**:
  1. Patch `IngestionScout.run_and_commit` to return `{"committed": False, "pending": True, "confidence": 0.5}`.
  2. Call `_dispatch_target` with `force_quarantine=True`.
  3. Assert `entry["committed"] is False`.
- **Verify**: `pytest tests/autonomy/test_topic_frontier.py::test_dispatch_summary_shows_not_committed_when_force_quarantine -q` passes.

## T-003 — Strengthen existing test: assert run_and_commit called with force_quarantine=True

- **Refs**: FR-3, AC-1, NFR-HITL-1, NFR-AUDIT-1
- **Owner**: @copilot
- **Status**: `[ ]`
- **Files**:
  - `backend/tests/autonomy/test_topic_frontier.py`
- **Steps**:
  1. In `test_sets_human_approval_when_adapter_requires_it`, add:
     `scout.run_and_commit.assert_called_once_with(ANY, force_quarantine=True)`.
  2. Change mock return to `{"committed": False, "pending": True}` (correct value).
- **Verify**: existing test still passes with the new assertion added.

## T-004 — Add integration test: requires_human_approval adapter produces PendingReview row

- **Refs**: FR-4, AC-3, NFR-COV-1
- **Owner**: @copilot
- **Status**: `[ ]`
- **Files**:
  - `backend/tests/autonomy/test_topic_frontier.py`
- **Steps**:
  1. Decorate test with `@pytest.mark.integration` and `@pytest.mark.django_db(transaction=True)`.
  2. Set `CELERY_TASK_ALWAYS_EAGER=True` via `settings` fixture.
  3. Create adapter stub with `requires_human_approval=True`, returning one `RawDoc`.
  4. Call `_node_dispatch` via `async_to_sync` (sync test body).
  5. Assert `PendingReview.objects.filter(source=raw_doc.source_url).exists()`.
  6. Assert dispatch summary entry has `committed=False`.
- **Verify**: `pytest tests/autonomy/test_topic_frontier.py::test_requires_human_approval_produces_pending_review_row -m integration -v` passes.

## T-005 — Quality gate

- **Refs**: AC-4, AC-5, NFR-COV-1, NFR-PERF-1
- **Owner**: @copilot
- **Status**: `[ ]`
- **Files**: none (gate only)
- **Steps**:
  1. Run `make test-backend` — must exit 0.
  2. Run `make lint` — must exit 0.
  3. Confirm `topic_frontier.py` and `scout.py` line coverage does not decrease.
- **Verify**: CI green; coverage report shows no regression.

---

## Done-When (Definition of Done)

- All tasks `[x]`.
- All `AC-*` from `spec.md` covered by passing tests.
- `make lint && make test` green.
- LegalBench delta: 0 pp (no reasoning changes per spec §11).

---

## Follow-ups Discovered

- BL-20260511-31 — Migrate `TopicFrontier` to a proper `StateGraph` (spec §13; separate spec warranted).
- BL-20260510-01 — Full Celery/Django-ORM integration path for `PendingReview` broader than this spec; track separately.
