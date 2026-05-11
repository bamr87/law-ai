// 007 — Fulltext indexes for hybrid retrieval (spec 015 FR-2).
// Lexical pre-filter for the hybrid GraphRAG retriever (spec 018) before
// vector top-K and graph expansion. Uses Neo4j's native fulltext index API.

CREATE FULLTEXT INDEX case_text_fulltext IF NOT EXISTS
  FOR (c:Case) ON EACH [c.title, c.holding_summary];

CREATE FULLTEXT INDEX statute_section_text_fulltext IF NOT EXISTS
  FOR (s:StatuteSection) ON EACH [s.heading, s.text, s.citation];

CREATE FULLTEXT INDEX ordinance_section_text_fulltext IF NOT EXISTS
  FOR (o:OrdinanceSection) ON EACH [o.heading, o.text, o.citation];

CREATE FULLTEXT INDEX regulation_text_fulltext IF NOT EXISTS
  FOR (r:Regulation) ON EACH [r.citation, r.text];

CREATE FULLTEXT INDEX derived_document_body_fulltext IF NOT EXISTS
  FOR (d:DerivedDocument) ON EACH [d.body];
