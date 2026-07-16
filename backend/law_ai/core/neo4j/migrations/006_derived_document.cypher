// 006 — DerivedDocument label, uniqueness + provenance existence (spec 015 FR-4).
// `DerivedDocument` is the first-class home for AI-generated outputs (analyses,
// summaries, briefs, holdings) so they can be filtered out of any query that
// must return only authoritative primary law.

CREATE CONSTRAINT derived_document_id_unique IF NOT EXISTS
  FOR (d:DerivedDocument) REQUIRE d.id IS UNIQUE;

CREATE CONSTRAINT derived_document_agent_version_exists IF NOT EXISTS
  FOR (d:DerivedDocument) REQUIRE d.agent_version IS NOT NULL;

CREATE CONSTRAINT derived_document_kind_exists IF NOT EXISTS
  FOR (d:DerivedDocument) REQUIRE d.kind IS NOT NULL;
