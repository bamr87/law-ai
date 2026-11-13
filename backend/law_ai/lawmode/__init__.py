"""lawmode — advisory legal-risk review for source code, folded into Law AI.

Spec 057 (PRD §5.8, catalog LAWAI-022). This app holds the domain that came
over from the imported ``lawmode/`` tree: the finding and report schemas
(:mod:`law_ai.lawmode.schemas`), the policy (:mod:`law_ai.lawmode.policy`) and
the review service (:mod:`law_ai.lawmode.services`).

What did **not** come over is lawmode's own provider layer. This app has no
model client and no model default: every model call goes through
:mod:`law_ai.core.llm` — the ``LLM_PROVIDER_CHAIN`` — and is recorded through
:mod:`law_ai.core.provenance`. A finding is advisory; the critical and high
ones are for a human to decide on, never for this code to pass or fail.
"""
