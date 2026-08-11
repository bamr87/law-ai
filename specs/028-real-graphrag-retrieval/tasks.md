# Tasks: Real GraphRAG Retrieval (Lexical + Citation Expansion)

Spec: [spec.md](spec.md) · Plan: [plan.md](plan.md)

- [x] **T-001** — Create the `agents_runtime/tools/` package (FR-1)
  - Closes the AGENTS.md structural drift: the documented tools package
    did not exist; the tool layer lived scattered in `core/neo4j/`.
- [x] **T-002** — Lexical retrieval leg (FR-2, FR-3, FR-5, FR-6, NFR-SEC-1, AC-2, AC-7)
  - `case_text_fulltext` + `statute_section_text_fulltext` via
    `db.index.fulltext.queryNodes`, `escape_lucene` on all user text,
    substring fallback on index error (`index_available=False`),
    jurisdiction filtering by `court` prefix / `jurisdiction_code`,
    `archived_at IS NULL` everywhere.
- [x] **T-003** — Citation graph-expansion leg (FR-4, AC-1)
  - One `CITES` hop off the lexical seeds, ranked by seed-citation count,
    tagged `retrieval_mode="cites_expansion"`.
- [x] **T-004** — Attribution + audit on every passage and query (FR-7, FR-8, NFR-AUDIT-1, AC-6)
  - Passages carry court/decided_at/source/source_url/confidence;
    `_run_logged` routes every `session.run` through
    `provenance.log_graph_query`.
- [x] **T-005** — Coverage envelope (FR-9, AC-3, NFR-PERF-1)
  - `RetrievalCoverage` + `note()`; `RetrievalStats` gains
    `lexical_count`, `expanded_count`, `jurisdictions_present`,
    `jurisdiction_absent`; `_retrieve` **returns** coverage so LangGraph
    merges it into state; `invoke` maps it onto the output.
- [x] **T-006** — Wire as `LegalWorkflow`'s default + attribution prompt (FR-10, FR-11, AC-4, AC-5)
  - `_build_default_retriever()` replaces the `[]` stub; retriever built in
    `__init__` (no connection opened); `analyze` prompt renders court/date
    per passage and demands attributed citations or an explicit refusal;
    all faults degrade to `[]`.
- [x] **T-007** — Unit tests with a fake Neo4j session (AC-1 … AC-7)
  - `tests/agents/tools/test_graph_rag.py`: 12 tests covering both legs,
    fallback, absent jurisdiction, total failure, zero-query short-circuit,
    provenance logging, and Lucene escaping. Full backend suite green
    (coverage 81.23%), mypy clean on touched modules.

## Follow-ups Discovered

- Vector/embedding leg for GraphRAG: no embedding property exists on
  `:Case`/`:StatuteSection`, so this retriever is lexical + citation
  expansion only. Add nomic-embed-text embeddings at ingest, a Neo4j vector
  index, and reciprocal-rank fusion with the lexical leg.
- Integration test against real Neo4j (marker `integration`): seed
  `:Case` + `:CITES` fixtures and assert fulltext hits, expansion,
  jurisdiction filtering, and that `log_graph_query` rows actually land —
  today only fake-session unit tests cover the retriever.
- Populate `:Case.holding_summary` during extraction: it is indexed for
  fulltext and used as the passage snippet, but the CourtListener extractor
  never sets it, so passages degrade to "(no holding summary stored)".
- A first-class `jurisdiction` property on `:Case` would replace the
  `court`-prefix heuristic this retriever inherits from
  `list_under_cited_jurisdictions`.
