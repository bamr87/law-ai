# Tasks: Close the Ingestion HITL Loop (Approval → Graph)

Spec: [spec.md](spec.md) · Plan: [plan.md](plan.md)

- [x] **T-001** — Model + migration for review attribution and commit state (FR-1, NFR-IDEMPOTENT-1)
  - `reviewer`, `review_note`, `committed_at`, `commit_error` + `is_committed` / `awaits_commit`; migration `0003` follows the `SeparateDatabaseAndState` vendor-aware precedent with an `(approved, committed_at)` sweep index. Verified: `makemigrations --check` clean, applied against real Postgres (`\d pending_review` shows all four columns and both indexes) and the SQLite test DB.
- [x] **T-002** — `force_commit` on the sole graph writer (FR-4, NFR-SEC-1)
  - `IngestionScout.run_and_commit` bypasses the confidence gate for human-approved items; `force_quarantine` still wins, so approval-required sources can never auto-commit. §12 I1 preserved — no second writer introduced.
- [x] **T-003** — Make `ENABLE_HUMAN_APPROVAL_GATES` live and audited (FR-8, NFR-AUDIT-1)
  - Read at call time; disabling it skips quarantine and emits a `hitl_gate_disabled` provenance event per item (§5 override leaves a trace). Default remains `True`.
- [x] **T-004** — Approval service (FR-2, FR-3, FR-5, FR-9, AC-1, AC-4, AC-5, AC-6, AC-7)
  - `record_decision`, `commit_approved_review`, `commit_approved_reviews`; envelope + legacy flat payload recovery; failures persist `commit_error`, keep the row approved+uncommitted for retry, and emit `quarantine_commit_failed`.
- [x] **T-005** — Three operator surfaces (FR-6, FR-7, AC-8)
  - Celery `commit_approved_reviews_task`; admin *Approve + commit selected* / *Reject selected* (records the Django user as reviewer); `manage.py review_queue {list,show,approve,reject,commit}` where `show` surfaces the quarantine reason + full payload so a human can see WHY.
- [x] **T-006** — Tests (AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7, AC-8, NFR-IDEMPOTENT-1)
  - `tests/ingestion/test_approval_commit.py` — 9 tests, no Neo4j needed: commit path with `force_commit=True` (AC-1); pending/rejected rows are never committed (AC-2); a second sweep is a no-op (AC-3); graph failure recorded and retryable (AC-4); `ApprovalError` on unapproved rows (AC-5); decision attribution (AC-6); legacy flat payload (AC-7); Celery task counts (AC-8). Full ingestion suite (61) and full backend suite green.

## Follow-ups Discovered

- Frontend quarantine review queue: the surfaces here are admin + CLI, so
a non-operator reviewer still cannot work the queue from the web app (the UI half of BL-20260810-03).
- Celery beat entry for `commit_approved_reviews_task` under
`AUTONOMY_ENABLED`, so approvals flow to the graph without a manual sweep — mirroring the spec 019 beat pattern, budget-capped.
- Statute/ordinance commit path: `commit_approved_review` routes every
`kind` through `IngestionScout` (a `:Case` extractor). Rows with `kind="statute_section"` need `StatuteScout.run_and_commit` dispatch before statute approvals can be committed.
- Reviewer identity is a free-text string; wire it to real Django auth
users (FK) once the platform has user accounts, and record the same attribution on LSAT proposal decisions (rest of BL-20260810-08).
