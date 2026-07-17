# Cite Check Node — Spec 010 / LegalWorkflow

**Version**: 1 **Model**: deterministic (no LLM call) **Inputs**: citations from `analyze` **Output**: per-citation verification status

This node does NOT call an LLM. It uses `app.db.citation_resolver.resolve_citations` to confirm each citation maps to a real `:Case` node in Neo4j. Any citation that fails to resolve is flagged with `source: "ollama-hallucination-check"` and the workflow output sets `human_approval_required = True`.
