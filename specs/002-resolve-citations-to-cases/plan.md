# Plan: 002 — Resolve Citations to Case Nodes

## Approach

1. Extend `ExtractionResult` with an optional `aliases: list[str]` (default `[]`). Threaded through `MERGE_CASE_CYPHER` so freshly-ingested cases register their canonical citation forms.
2. New module [backend/app/db/citation_resolver.py](../../backend/app/db/citation_resolver.py) with two pure-async functions and one batched Cypher query.
3. Wire `densify_extraction` into `IngestionScout.run_and_commit` between `extract` and `commit_extraction`.
4. Add provenance hook so each resolution emits an audit record.

## Cypher

```cypher
UNWIND $normalized AS n
OPTIONAL MATCH (c:Case)
WHERE n IN coalesce(c.aliases, [])
RETURN n AS normalized, head(collect(c.id)) AS case_id
```

- One round-trip regardless of input length (NFR-PERF-1).
- `head(collect(...))` deterministic on alias collisions (lexicographically smallest first via secondary sort if needed; first iteration ships with non-deterministic `head` and a follow-up to add a deterministic tie-break).

## Idempotency Argument

`MERGE_CITES_CYPHER` is the existing `MERGE` on the `(src,dst)` pair, so re-running with the same `target_case_id` is a no-op. Resolver itself is read-only, so it's trivially idempotent.

## Test Strategy

- Pure unit tests with a `FakeAsyncSession` recording calls and returning canned cursors. No Docker required for the green path (constitution §3 — fast tests).
- Integration test gated behind `@pytest.mark.integration` mirroring spec 001 pattern (BL-20260429-01 will close that gap globally; this spec inherits the marker).

## Migration

Add `backend/app/db/neo4j_migrations/002_case_aliases.cypher`:

```cypher
MATCH (c:Case) WHERE c.aliases IS NULL SET c.aliases = [];
```

Run by the existing migration runner on next `make dev`.

## Risk Mitigations

- `R-1` (bad aliases): `:CITES.confidence` inherits source confidence, HITL gate upstream.
- `R-2` (backfill): added to follow-ups, not in this spec.
