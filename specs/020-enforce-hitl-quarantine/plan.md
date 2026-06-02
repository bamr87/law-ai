# Plan: Enforce HITL Quarantine for requires_human_approval Adapters

## Summary

The `force_quarantine` mechanism was already implemented in spec 018 across
`TopicFrontier._node_dispatch` → `_dispatch_target` → `IngestionScout.run_and_commit`.
This spec adds the missing test coverage to verify the contract end-to-end.

## Approach

1. Add a unit test in `test_topic_frontier.py` that asserts `run_and_commit` is
   called with `force_quarantine=True` when the adapter has `requires_human_approval=True`.
2. Add a unit test in `test_scout.py` that asserts a high-confidence document
   (confidence ≥ 0.7) is quarantined when `force_quarantine=True` is passed.
3. Update `BACKLOG.md`: move BL-20260511-30 to Done, add follow-up items.

## Risks

None — pure test addition; no production code changes.
