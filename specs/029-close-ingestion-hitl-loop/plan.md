# Plan: Close the Ingestion HITL Loop (Approval → Graph)

- **Spec**: [spec.md](spec.md) (029-close-ingestion-hitl-loop)
- **Approach**: keep **approval** and **commit** as two distinct persisted
states so a graph outage can never discard a reviewer's decision, and route the actual write through the one sanctioned writer rather than adding a second one (constitution §12 I1).

## Why two states

`approved` alone cannot express "a human said yes but the graph write failed". Splitting into `approved` (human intent) + `committed_at` (system outcome) + `commit_error` (why not) makes the handoff idempotent, retryable, and auditable — and makes a stuck row visible instead of looking done.

## Steps

1. **Model + migration** — `reviewer`, `review_note`, `committed_at`,
`commit_error` on `PendingReview`, plus `is_committed` / `awaits_commit` helpers. Migration `0003` copies the 0001/0002 pattern exactly: `SeparateDatabaseAndState`, Postgres `ADD COLUMN IF NOT EXISTS` (adopts the legacy spec-004 table in place), SQLite portable form for the test fixture, plus a `(approved, committed_at)` index for the sweep query. All columns nullable/defaulted so existing rows back-fill correctly.
2. **`IngestionScout.run_and_commit(force_commit=...)`** — the approval path
must bypass the confidence gate that quarantined the row in the first place, but `force_quarantine` keeps precedence so approval-required sources can never auto-commit. Same method stays the sole `:Case` writer.
3. **Live HITL gate** — `_hitl_gates_enabled()` reads
`ENABLE_HUMAN_APPROVAL_GATES` at call time (not import time, so tests and operators can flip it per-run); disabling it skips quarantine **and** emits a `hitl_gate_disabled` provenance event per item, because §5 says the gate is mandatory and an override must leave a trace.
4. **`services/approval.py`** — `record_decision` (attribution + rationale
   + `quarantine_decision` event), `commit_approved_review` (state checks,
payload recovery for both envelope and legacy flat shapes, commit, persist outcome, emit `quarantine_committed` / `quarantine_commit_failed`), `commit_approved_reviews` (bounded idempotent sweep). Async ORM writes go through `sync_to_async`.
5. **Three operator surfaces**, all delegating to the same service: Celery
task `commit_approved_reviews_task`, admin actions *Approve + commit* / *Reject*, and `manage.py review_queue`. The admin records the Django user as reviewer; the CLI takes `--reviewer` and warns when it is omitted.
6. **`review_queue show`** answers the audit's "a human cannot see WHY
something is quarantined": reason, confidence, review state, commit error, and the full payload.

## Test strategy

`tests/ingestion/test_approval_commit.py` (9 tests) with `IngestionScout.run_and_commit` mocked so no Neo4j is needed: commit path (asserting `force_commit=True` and the unwrapped payload), pending/rejected never committed, idempotent second sweep, graph-failure recording + retry state, `ApprovalError` on unapproved rows, legacy flat payload, decision attribution, and the Celery task summary.

Verification beyond unit tests: `makemigrations --check` clean (state matches the model), migration applied against **real Postgres** with columns and indexes confirmed via `\d pending_review`, and the full ingestion suite green.

## Rollback

`migrate ingestionapp 0002` reverses the columns (the reverse SQL is written); the service and surfaces are additive and can be reverted independently. No Neo4j data is touched by the rollback.
