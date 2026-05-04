# Data Model

LexGraph AI's Neo4j knowledge graph. Spec of record: [001-ingest-courtlistener-opinions](../specs/001-ingest-courtlistener-opinions/spec.md).

## Nodes

### `Case`
| Property            | Type     | Notes                                  |
| ------------------- | -------- | -------------------------------------- |
| `id` (UNIQUE)       | string   | Source-prefixed, e.g. `12345`          |
| `title`             | string   | Case caption                           |
| `court`             | string   | e.g. "Supreme Court"                   |
| `decided_date`      | date     | ISO YYYY-MM-DD, optional               |
| `source`            | string   | e.g. `courtlistener`                   |
| `source_url`        | string   | Canonical URL                          |
| `confidence`        | float    | 0..1; ≥0.7 commits, < goes to review   |
| `ingest_timestamp`  | datetime | UTC                                    |
| `agent_version`     | string   | e.g. `0.1.0`                           |

### `Citation`
| Property                | Type   | Notes                                |
| ----------------------- | ------ | ------------------------------------ |
| `normalized` (UNIQUE)   | string | Lowercased eyecite reporter form     |
| `text`                  | string | Verbatim citation text               |

## Edges

- `(:Case)-[:HAS_CITATION]->(:Citation)` — opinion contains citation text.
- `(:Case)-[:CITES {confidence,context}]->(:Case)` — created when a `Citation` resolves to another known `Case` (downstream — out of scope for spec 001).

## Constraints

Defined in [backend/app/db/neo4j_migrations/001_case_constraints.cypher](../backend/app/db/neo4j_migrations/001_case_constraints.cypher):
- `CREATE CONSTRAINT case_id_unique ... ASSERT (c.id) IS UNIQUE`
- `CREATE CONSTRAINT citation_normalized_unique ... ASSERT (cit.normalized) IS UNIQUE`

## Idempotency

All writes use `MERGE` keyed on the unique property, so re-running ingestion against the same source IDs creates **0 duplicate** nodes/edges (AC-2).

## Quarantine

Items below `confidence = 0.7` never enter the graph; they land in `pending_review` (Postgres table or JSONL fallback at `backend/var/pending_review/<date>.jsonl`).
