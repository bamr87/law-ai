// 006 — DerivedDocument label, uniqueness + provenance existence (spec 015 FR-4).
// `DerivedDocument` is the first-class home for AI-generated outputs (analyses,
// summaries, briefs, holdings) so they can be filtered out of any query that
// must return only authoritative primary law.

CREATE CONSTRAINT derived_document_id_unique IF NOT EXISTS
  FOR (d:DerivedDocument) REQUIRE d.id IS UNIQUE;

// The two property-existence constraints below are Enterprise-only. The pinned
// `neo4j:5-community` image rejects them, so `migrate_neo4j` defers this whole
// file (see `is_enterprise_only` in core/neo4j/migrator.py) and no dev or CI
// database actually holds them — BL-20260905-87. Until the graph can enforce
// it, `law_ai.core.schemas.legal_documents.DerivedDocument` is where the
// invariant lives: `kind` and `agent_version` are required, non-null fields on
// the model every write path must go through, and
// tests/models/test_legal_document_schemas.py holds that line.

CREATE CONSTRAINT derived_document_agent_version_exists IF NOT EXISTS
  FOR (d:DerivedDocument) REQUIRE d.agent_version IS NOT NULL;

CREATE CONSTRAINT derived_document_kind_exists IF NOT EXISTS
  FOR (d:DerivedDocument) REQUIRE d.kind IS NOT NULL;
