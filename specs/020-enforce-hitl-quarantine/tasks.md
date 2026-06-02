# Tasks: Enforce HITL Quarantine for requires_human_approval Adapters

## Tasks

- [x] T-001 (FR-1) — Add `test_force_quarantine_passed_when_adapter_requires_approval` to `test_topic_frontier.py` (AC-1)
- [x] T-002 (FR-2, NFR-HITL-1) — Add `test_force_quarantine_routes_high_confidence_to_hitl` to `test_scout.py` (AC-2)
- [x] T-003 — Move BL-20260511-30 from `## Open` to `## Done` in BACKLOG.md
- [x] T-004 — Add follow-up items BL-20260602-01, BL-20260602-02 to `## Open`
- [x] T-005 — Verify spec_validator and backlog_lint gates

## Follow-ups Discovered

- **BL-20260602-01** — *test-gap, low* — Integration test for `force_quarantine` against live Docker stack.
- **BL-20260602-02** — *doc-gap, low* — Document `requires_human_approval` contract in `docs/architecture.md`.
