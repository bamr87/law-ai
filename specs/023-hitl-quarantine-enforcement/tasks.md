# Tasks: HITL Quarantine Enforcement — Test Coverage & Regression Guard

> Each task must reference one or more `FR-*` / `NFR-*` / `AC-*` IDs from `spec.md`. CI's [spec_validator.py](../../scripts/spec_validator.py) enforces that every requirement in `spec.md` is referenced by at least one task.

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: GitHub handle or `@copilot` / `@agent:<role>`.

---

> NOTE: The test module is `backend/tests/agents/graphs/test_topic_frontier.py`.
> Verify commands run Docker-first (`docker compose run --rm backend pytest …`).

## T-001 — Add unit test: force_quarantine=True propagates to run_and_commit

- **Refs**: FR-1, AC-1, NFR-PERF-1, NFR-HITL-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/tests/agents/graphs/test_topic_frontier.py`
- **Steps**:
  1. Create an adapter stub with `requires_human_approval=True`.
  2. Patch `scout.run_and_commit` with `mocker.patch`.
  3. Call `_node_dispatch` and capture `call_args`.
  4. Assert `call_kwargs["force_quarantine"] is True`.
- **Verify**: Satisfied by existing `test_force_quarantine_passed_when_adapter_requires_approval`
  (added under BL-20260511-30 / spec 020); asserts `kwargs["force_quarantine"] is True`.

## T-002 — Add unit test: dispatch summary records committed=False when force_quarantine=True

- **Refs**: FR-2, AC-2, NFR-PERF-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/tests/agents/graphs/test_topic_frontier.py`
- **Steps**:
  1. Patch `IngestionScout.run_and_commit` to return `{"committed": False, "pending": True, "confidence": 0.5}`.
  2. Call `_dispatch_target` with `force_quarantine=True`.
  3. Assert `entry["committed"] is False`.
- **Verify**: `docker compose run --rm --no-deps backend pytest tests/agents/graphs/test_topic_frontier.py::test_dispatch_summary_shows_not_committed_when_force_quarantine -q` passes.

## T-003 — Strengthen existing test: assert run_and_commit called with force_quarantine=True

- **Refs**: FR-3, AC-1, NFR-HITL-1, NFR-AUDIT-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/tests/agents/graphs/test_topic_frontier.py`
- **Steps**:
  1. In `test_sets_human_approval_when_adapter_requires_it`, add:
     `scout.run_and_commit.assert_called_once_with(ANY, force_quarantine=True)`.
  2. Change mock return to `{"committed": False, "pending": True}` (correct value).
- **Verify**: existing test still passes with the new assertion added.

## T-004 — Add integration test: requires_human_approval adapter produces PendingReview row

- **Refs**: FR-4, AC-3, NFR-COV-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/tests/agents/graphs/test_topic_frontier.py`
- **Steps**:
  1. Decorate test with `@pytest.mark.integration` and `@pytest.mark.django_db(transaction=True)`.
  2. Set `CELERY_TASK_ALWAYS_EAGER=True` via `settings` fixture.
  3. Create adapter stub with `requires_human_approval=True`, returning one `RawDoc`.
  4. Call `_node_dispatch` via `async_to_sync` (sync test body).
  5. Assert the `PendingReview` row exists. **Correction**: scout's `OpinionExtractor`
     hardcodes `source="courtlistener"` and stores the doc URL as the row PK, so the
     lookup is `PendingReview.objects.filter(pk=raw_doc.source_url).exists()`, not
     `filter(source=...)` as originally drafted in FR-4.
  6. Assert dispatch summary entry has `committed=False`.
- **Verify**: `docker compose run --rm backend pytest tests/agents/graphs/test_topic_frontier.py::test_requires_human_approval_produces_pending_review_row -m integration -v` passes.

## T-005 — Quality gate

- **Refs**: AC-4, AC-5, NFR-COV-1, NFR-PERF-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**: none (gate only)
- **Result**: `make test-backend` green (coverage 81.76% ≥ 75%); `make lint` exit 0
  (ruff + black clean on the test file; 8 pre-existing frontend warnings, 0 errors).
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
- BL-20260602-07 — FR-4 in this spec drafted the integration assertion as
  `PendingReview.objects.filter(source=raw_doc.source_url)`, but scout's
  `OpinionExtractor` hardcodes `source="courtlistener"` and stores the doc URL as
  the row PK — so the row is looked up by `pk`, not `source`. The dispatch chain
  passes a `RawDoc`-shaped payload through the CourtListener extractor regardless
  of the originating adapter; a dedicated per-adapter extractor would let
  `PendingReview.source` reflect the true source. Surfaced in: specs/023.
