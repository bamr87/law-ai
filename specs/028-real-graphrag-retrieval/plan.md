# Plan: Real GraphRAG Retrieval (Lexical + Citation Expansion)

- **Spec**: [spec.md](spec.md) (028-real-graphrag-retrieval)
- **Approach**: build the tool as a standalone, fully unit-testable object
  first (fake Neo4j session — no DB needed), then wire it as the workflow
  default. Read-only against the existing schema, so there is no migration
  and no data risk.

## Steps

1. **Create the `tools/` package** AGENTS.md documents but which never
   existed: `agents_runtime/tools/{__init__,graph_rag}.py`.
2. **Cypher, schema-accurate** — verified against the real node shapes
   before writing: `:Case` has `id/title/court/decided_at/source/
   source_url/confidence` (no `jurisdiction` property → filter by lowercase
   `court` prefix, the convention `list_under_cited_jurisdictions` already
   uses); `:StatuteSection` carries `jurisdiction_code`. Every statement
   `LIMIT`-bounded, parameter-bound, and `archived_at IS NULL`.
3. **`GraphRAGRetriever`**:
   - `_lexical_cases` → `case_text_fulltext`, with `escape_lucene` on the
     query and a substring-scan fallback on any index error.
   - `_lexical_statutes` → `statute_section_text_fulltext` (skipped, not
     fatal, when unavailable).
   - Expansion → `EXPAND_CITES_CYPHER` over the lexical seed ids.
   - `_run_logged` wraps every `session.run` with
     `provenance.log_graph_query`.
   - Dedup by node id; `last_coverage` published per run.
   - Top-level `except` → `[]` so a graph fault degrades to the refusal
     path rather than raising into the API.
4. **`RetrievalCoverage.note()`** composes the reviewer-facing caveat:
   empty-corpus wording, result mix, jurisdictions represented, and an
   explicit absent-jurisdiction warning.
5. **Wire into `LegalWorkflow`**: `_build_default_retriever()` replaces the
   `[]` stub; the retriever is built in `__init__` (no connection opened) so
   `_retrieve` can read `last_coverage` and **return** it — returning is what
   merges into LangGraph state; mutating the input state would not.
   `LegalWorkflowState` gains `retrieval_coverage`; `RetrievalStats` gains
   the four new fields; `invoke` merges them with a sensible default note.
6. **Attribution in the prompt**: `_analyze` renders `title — court (date)`
   per passage and instructs the model to name the issuing authority and to
   refuse rather than answer from general knowledge.
7. **Typing**: `__call__` takes `Mapping[str, Any]` (a supertype of the
   `LegalWorkflowState` TypedDict) so it satisfies the `Retriever` callable
   type under parameter contravariance.

## Test strategy

`tests/agents/tools/test_graph_rag.py` with a `FakeSession` routing Cypher
by distinctive substring (the two fulltext statements share the
`db.index.fulltext.queryNodes` prefix, so routing keys on the RETURN
projection instead): lexical+expansion, index-missing fallback, absent
jurisdiction, total failure, no-queries-no-DB-calls, provenance logging,
and `escape_lucene` behavior. Existing workflow tests must stay green
unchanged (they inject their own retriever, so the default swap is
invisible to them).

Gates: `make test-backend` (full suite, DBs up), `ruff`/`black`,
`mypy --strict` on the touched modules, `make lint-specs`.

## Rollback

Revert the commit; the workflow falls back to the stub. No migrations, no
schema changes, no data writes (the retriever is read-only).
