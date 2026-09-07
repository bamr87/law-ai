# Cite Check Node — Spec 010 / LegalWorkflow

**Version**: 2 **Model**: deterministic (no LLM call) **Inputs**: citations from `analyze` **Output**: per-citation verification status

This node does NOT call an LLM. It uses `app.db.citation_resolver.resolve_citations` to confirm each citation maps to a real `:Case` node in Neo4j. Any citation that fails to resolve is flagged with `source: "ollama-hallucination-check"` and the workflow output sets `human_approval_required = True`.

## v2 — §13 attribution gate (BL-20260803-04)

`cite_check` now also runs `law_ai.agents_runtime.attribution.check_attribution` over the citations. Any citation missing court, jurisdiction or decided_at appends a note and forces `human_approval_required`, independently of whether the citation resolved to a `:Case` id. Attribution is read off the retrieved passage, never restated by the model.
