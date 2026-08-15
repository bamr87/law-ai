# Spec: Close the Ingestion HITL Loop (Approval → Graph)

- **ID**: 029-close-ingestion-hitl-loop
- **Status**: shipped
- **Owner**: @bamr87
- **Created**: 2026-08-11
- **Roadmap Epic**: continuous-evolution hardening (2026-08-10 audit)
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md) — §4 (provenance + reviewer attribution), §5 (HITL on ingestion), §12 I1 (single graph writer), §13 (no fabrication)

## 1. Problem & Motivation

`PendingReview.approved` had **no consumer anywhere in the codebase** (verified by repo-wide grep). A human could approve a quarantined document in Django admin and *nothing happened* — the approved knowledge never reached Neo4j. The sanctioned HITL path could not grow the corpus at all, which also caps the value of the retriever shipped in spec 028: retrieval is bounded by a corpus that had no working intake path.

Two related dead ends: `ENABLE_HUMAN_APPROVAL_GATES` appeared only in settings (never read), and review decisions recorded **no reviewer and no rationale** — unacceptable on a platform whose differentiator is auditability.

## 2. Goals

- G1: Approving a quarantined item actually commits it to the knowledge
  graph, through the one sanctioned writer (BL-20260810-03).
- G2: Every review decision records **who** decided and **why**
  (BL-20260810-08).
- G3: A failed graph write is visible and retryable, never silently lost.
- G4: `ENABLE_HUMAN_APPROVAL_GATES` becomes a real, audited control.
- G5: Operators can see *why* something was quarantined and action it
  without the Django admin.

## 3. Non-Goals

- NG1: A frontend quarantine review UI (the CLI + admin are the surfaces
  here; the web UI remains BL-20260810-03's frontend half).
- NG2: Bulk auto-approval or any confidence-based auto-commit — that would
  defeat §5.
- NG3: Statute/ordinance commit paths (`StatuteScout`) — this spec closes
  the `:Case` loop; the statute kinds reuse the same row states.

## 4. User Stories

- As a reviewer, I want approving a document to actually add it to the
  knowledge graph, so my review work has an effect.
- As an auditor, I want to see who approved what and why, so review
  decisions are attributable.
- As an operator, I want a failed commit to be visible and retried, not
  silently marked approved.

## 5. Functional Requirements

- **FR-1**: `PendingReview` gains `reviewer`, `review_note`, `committed_at`,
`commit_error`, plus `is_committed` / `awaits_commit` properties; migration `0003` follows the established `SeparateDatabaseAndState` vendor-aware pattern (Postgres `IF NOT EXISTS`, SQLite portable form) and back-fills existing rows to "never reviewed, never committed".
- **FR-2**: `record_decision(review, approved, reviewer, note)` persists the
decision and emits a `quarantine_decision` provenance event carrying the reviewer and rationale.
- **FR-3**: `commit_approved_review(review)` commits one approved row via
`IngestionScout.run_and_commit(..., force_commit=True)`; it refuses rows that are not `approved is True` and skips already-committed rows.
- **FR-4**: `IngestionScout.run_and_commit` accepts `force_commit` to bypass
the confidence gate (the human approval *is* the gate). `force_quarantine` takes precedence, so an approval-required source can never auto-commit.
- **FR-5**: Commit failures set `commit_error`, leave `committed_at` NULL and
`approved` True (so the next sweep retries), and emit `quarantine_commit_failed`.
- **FR-6**: `commit_approved_reviews(limit)` sweeps approved-uncommitted rows
idempotently; exposed as Celery task `commit_approved_reviews_task`, the admin action *Approve + commit selected*, and `manage.py review_queue commit`.
- **FR-7**: `manage.py review_queue {list,show,approve,reject,commit}` with
`--reviewer` / `--note` / `--state` / `--limit`; `show` prints the quarantine reason, confidence, and full payload so a human can see **why** it was held.
- **FR-8**: `ENABLE_HUMAN_APPROVAL_GATES` is read at call time by
`run_and_commit`; when disabled, quarantine is skipped **and** a `hitl_gate_disabled` provenance event is emitted per item (§5 override must leave a trace). Default stays `True`.
- **FR-9**: Payload recovery accepts both the Celery envelope
(`{id, source, confidence, reason, payload}`) and legacy spec-004 flat rows.

## 6. Non-Functional Requirements

- **NFR-AUDIT-1**: Decision, commit, commit-failure, and gate-disable all
  emit provenance events via `core.provenance`.
- **NFR-IDEMPOTENT-1**: Re-running a sweep never double-writes; committed
  rows are filtered out at the query level.
- **NFR-SEC-1**: No new graph writer is introduced — §12 I1 preserved.

## 7. Data Model Impact

Postgres `pending_review`: four new nullable/defaulted columns and two indexes (`committed_at`, `(approved, committed_at)`). No Neo4j schema change. Migration verified against real Postgres and the SQLite test DB; `makemigrations --check` is clean.

## 8. API Surface

No HTTP routes. New operator surfaces: Celery task `law_ai.ingestionapp.commit_approved_reviews`, admin actions *Approve + commit selected* / *Reject selected*, and the `review_queue` management command.

## 9. Agent / Crew Impact

`IngestionScout.run_and_commit` gains `force_commit` and the live HITL-gate check. No new agents.

## 10. Acceptance Criteria

- **AC-1**: Approving a quarantined row and sweeping commits it via
`IngestionScout.run_and_commit` with `force_commit=True`, sets `committed_at`, and clears `commit_error`.
- **AC-2**: Rows that are pending or rejected are never committed.
- **AC-3**: A second sweep after a successful commit is a no-op (idempotent).
- **AC-4**: A graph failure records `commit_error`, leaves the row approved
  and uncommitted, and emits `quarantine_commit_failed`.
- **AC-5**: `commit_approved_review` on an unapproved row raises
  `ApprovalError`.
- **AC-6**: `record_decision` persists reviewer + note and emits
  `quarantine_decision` with the reviewer named.
- **AC-7**: Legacy flat payloads commit correctly.
- **AC-8**: The Celery task reports `{processed, committed, failed}`.

## 11. LegalBench Impact

- Tasks affected: none directly (ingestion path, no reasoning change).
- Expected delta: 0 pp now; indirectly positive over time, since this is
  the only sanctioned way the corpus behind `precedent_retrieval` grows.

## 12. Risks & Open Questions

- **R-1**: `force_commit` is a real bypass of the confidence gate. It is
reachable only from the approval path, `force_quarantine` overrides it, and every use is preceded by a persisted human decision.
- **R-2**: Re-extraction at commit time means the committed document is
re-parsed from the stored payload; if the extractor changed since quarantine, the committed result reflects the *current* extractor. That is the desired behavior (bug fixes apply) but is worth noting.

## 13. Out of Scope / Follow-ups

See `tasks.md` → `## Follow-ups Discovered` (mirrored into BACKLOG.md as BL-20260811-01 … BL-20260811-04).
