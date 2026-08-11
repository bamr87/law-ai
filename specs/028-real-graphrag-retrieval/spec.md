# Spec: Real GraphRAG Retrieval (Lexical + Citation Expansion)

- **ID**: 028-real-graphrag-retrieval
- **Status**: shipped
- **Owner**: @bamr87
- **Created**: 2026-08-11
- **Roadmap Epic**: continuous-evolution hardening (closes the keystone gap from the 2026-08-10 audit)
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md) — §4 (every retrieval logged, provenance on every passage), §13 (attribution + absence reporting), §2 (Neo4j-native Cypher, no new frameworks)

## 1. Problem & Motivation

`LegalWorkflow`'s retriever was a stub that returned `[]`. Because spec 027
made LangGraph the default engine, that stub meant **every production
analysis took the insufficient-sources refusal path** — the platform could
not answer anything from its own knowledge graph, no matter how much had
been ingested. Meanwhile `007_fulltext_indexes.cypher` had already created
the fulltext indexes the retriever needed, and `AGENTS.md` documented an
`agents_runtime/tools/` package (Neo4j, CourtListener, GraphRAG tools) that
did not exist on disk.

Retrieval is also where constitution §13 is won or lost: passages must carry
the authority that issued them, and a thin or jurisdictionally lopsided
result set must say so rather than reading as "no such law."

## 2. Goals

- G1: A real retriever that returns grounded passages from Neo4j, wired as
  `LegalWorkflow`'s default (BL-20260810-01).
- G2: GraphRAG, not plain search — traverse `CITES` so authorities the seed
  cases rely on surface even when their text doesn't match the query.
- G3: Every passage carries §13 attribution; every Cypher call is audited.
- G4: Report coverage honestly — result mix, jurisdictions actually
  represented, and an explicit flag when the requested jurisdiction returned
  nothing.
- G5: Create the `agents_runtime/tools/` package AGENTS.md specifies.

## 3. Non-Goals

- NG1: Vector/embedding retrieval — no embedding property exists on `:Case`
  yet (BL-20260810-17). This spec ships the lexical + graph hybrid the
  current schema can honestly support.
- NG2: Re-ranking models or query rewriting beyond the existing `retrieve`
  node's LLM-drafted queries.
- NG3: Frontend rendering of the enriched envelope (BL-20260810-02).

## 4. User Stories

- As a lawyer, I want answers grounded in the cases actually in the corpus,
  with the court and date attached, so I can verify every proposition.
- As a reviewer, I want to know when the corpus had nothing for my
  jurisdiction, so I don't mistake a thin corpus for settled law.

## 5. Functional Requirements

- **FR-1**: New package `law_ai.agents_runtime.tools` with `graph_rag`
  exposing `GraphRAGRetriever`, `RetrievalCoverage`, `build_default_retriever`.
- **FR-2**: Lexical leg queries `case_text_fulltext` and
  `statute_section_text_fulltext` via `db.index.fulltext.queryNodes`, with
  Lucene metacharacter escaping on all user-derived text.
- **FR-3**: Substring fallback when the fulltext index is absent (fresh DB
  / migrations not applied), recorded as `index_available=False`.
- **FR-4**: Graph-expansion leg pulls one hop of `CITES` neighbours of the
  lexical seeds, ranked by how many seeds cite them, tagged
  `retrieval_mode="cites_expansion"`.
- **FR-5**: Jurisdiction filtering — `:Case` by lowercase `court` prefix
  (the corpus convention; there is no `jurisdiction` property on Case),
  `:StatuteSection` by `jurisdiction_code`.
- **FR-6**: Soft-delete respected everywhere (`archived_at IS NULL`), per §4.
- **FR-7**: Every passage carries `court`, `decided_at`, `source`,
  `source_url`, `confidence`, `retrieval_mode` (§13 attribution).
- **FR-8**: Every Cypher round-trip logged via `provenance.log_graph_query`
  with result count and latency (§4).
- **FR-9**: `RetrievalStats` extended with `lexical_count`,
  `expanded_count`, `jurisdictions_present`, `jurisdiction_absent`; the
  retriever's `last_coverage` is merged into graph state by the `retrieve`
  node's return value and surfaced through `IRACOutput.retrieval`.
- **FR-10**: The `analyze` prompt renders each passage with its court and
  decided date and instructs the model to name the issuing authority and to
  refuse rather than answer from general knowledge.
- **FR-11**: Any retrieval fault degrades to `[]` (⇒ the honest refusal
  path) — never an exception escaping into the API, never a fabrication.

## 6. Non-Functional Requirements

- **NFR-PERF-1**: All Cypher is `LIMIT`-bounded (default 8 lexical + 4
  expansion) and parameter-bound; no user text is interpolated into Cypher.
- **NFR-SEC-1**: Lucene escaping prevents query-syntax injection into the
  fulltext index; all filters use bound parameters.
- **NFR-AUDIT-1**: No retrieval path bypasses `log_graph_query`.

## 7. Data Model Impact

None — read-only against the existing schema. Uses the indexes created by
`007_fulltext_indexes.cypher`. Note `:Case.holding_summary` is indexed but
not currently populated by the extractor (BL-20260810-19).

## 8. API Surface

No route changes. `POST /api/analysis` responses now carry a populated
`irac.retrieval` envelope (previously always the empty/zero shape) with the
new `lexical_count` / `expanded_count` / `jurisdictions_present` /
`jurisdiction_absent` fields.

## 9. Agent / Crew Impact

`LegalWorkflow` gains a real default retriever and an attribution-carrying
`analyze` prompt. No new agents.

## 10. Acceptance Criteria

- **AC-1**: Given lexical hits and a `CITES` neighbour, the retriever
  returns both, tagged `lexical` and `cites_expansion`, with
  `expanded_count == 1`.
- **AC-2**: Given a fulltext index error, the retriever falls back to
  substring matching, still returns results, and sets
  `index_available=False`.
- **AC-3**: Given a requested jurisdiction with no matching results,
  `jurisdiction_absent` is True and the coverage note says so explicitly.
- **AC-4**: Given a total graph failure, retrieval returns `[]`, coverage
  says "does NOT mean no such law exists", and no exception escapes.
- **AC-5**: Given no queries, the retriever performs zero database calls.
- **AC-6**: Every executed Cypher statement appears in
  `provenance.log_graph_query` calls.
- **AC-7**: Passages carry court + decided_at; `escape_lucene` escapes
  Lucene metacharacters and leaves plain prose untouched.

## 11. LegalBench Impact

- Tasks affected: `precedent_retrieval` (the eval harness runs its own
  path today, so no measured delta until BL-20260810-04 lands).
- Expected delta: ≥ 0 pp. Retrieval can only add grounding where the stub
  guaranteed a refusal.

## 12. Risks & Open Questions

- **R-1**: Snippet quality is bounded by `holding_summary`, which the
  extractor does not populate yet — passages may read "(no holding summary
  stored)" until BL-20260810-19.
- **R-2**: Lexical-only matching misses paraphrases; the vector leg
  (BL-20260810-17) is the mitigation.
- **R-3**: Court-prefix jurisdiction filtering follows the existing corpus
  convention (`split(court,'-')[0]`); a first-class jurisdiction property on
  `:Case` would be cleaner.

## 13. Out of Scope / Follow-ups

See `tasks.md` → `## Follow-ups Discovered` (mirrored into BACKLOG.md as
BL-20260810-17 … BL-20260810-19).
