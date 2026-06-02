# Spec: Enforce HITL Quarantine for requires_human_approval Adapters

- **ID**: 020-enforce-hitl-quarantine
- **Status**: shipped
- **Owner**: @copilot
- **Created**: 2026-06-02
- **Roadmap Epic**: BL-20260511-30
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md) §5 (HITL Requirements)

## 1. Problem & Motivation

Constitution §5 mandates that any ingestion from a source flagged `requires_human_approval=True` MUST route through the HITL `PendingReview` queue regardless of extraction confidence. The `TopicFrontier._node_dispatch` node detected the flag and recorded it in state, but lacked verification that the `force_quarantine` parameter was propagated end-to-end through `IngestionScout.run_and_commit`.

## 2. Origin & Background

- **BL-20260511-30** — *feature, high* — Enforce `requires_human_approval=True` quarantine path in `TopicFrontier._node_dispatch`.
- Surfaced in: specs/018-autonomous-framework PR review.

## 3. Goals

- G1: Guarantee that when `SourceAdapter.requires_human_approval=True`, every `RawDoc` routes to `PendingReview` regardless of confidence score.
- G2: Add test coverage proving the `force_quarantine=True` flag propagates from `_node_dispatch` → `_dispatch_target` → `IngestionScout.run_and_commit`.

## 4. Non-Goals

- NG1: Changing the quarantine storage mechanism (Celery task + JSONL fallback remains as-is).
- NG2: Adding new source adapters with `requires_human_approval=True`.

## 5. Functional Requirements

- **FR-1**: `_node_dispatch` MUST pass `force_quarantine=True` to `_dispatch_target` when `adapter.requires_human_approval` is True.
- **FR-2**: `IngestionScout.run_and_commit(payload, force_quarantine=True)` MUST route to `_quarantine()` even when extraction confidence ≥ 0.7.

## 6. Non-Functional Requirements

- **NFR-HITL-1**: Matches constitution §5 — ingestion of a new public data source with HITL flag always queues for human review.

## 7. Acceptance Criteria

- **AC-1**: Given an adapter with `requires_human_approval=True`, when `_node_dispatch` processes a target, then `run_and_commit` is called with `force_quarantine=True`.
- **AC-2**: Given `force_quarantine=True` and a high-confidence payload (confidence ≥ 0.7), when `run_and_commit` executes, then the document is quarantined (committed=False, pending=True).

## 8. Verification

Implementation confirmed in:
- `backend/lawgraph/agents_runtime/graphs/topic_frontier.py` line 345
- `backend/lawgraph/ingestionapp/services/scout.py` line 134

Tests added:
- `backend/tests/agents/graphs/test_topic_frontier.py::TestNodeDispatch::test_force_quarantine_passed_when_adapter_requires_approval`
- `backend/tests/ingestion/test_scout.py::test_force_quarantine_routes_high_confidence_to_hitl`

## 9. Follow-ups Discovered

- **BL-20260602-01** — *test-gap, low* — Add an integration test that exercises the full `force_quarantine` path against a live Docker stack (adapter with `requires_human_approval=True` → Celery → PendingReview row). _Surfaced in:_ specs/020-enforce-hitl-quarantine.
- **BL-20260602-02** — *doc-gap, low* — Document the `requires_human_approval` adapter contract and its quarantine enforcement in `docs/architecture.md`. _Surfaced in:_ specs/020-enforce-hitl-quarantine.
