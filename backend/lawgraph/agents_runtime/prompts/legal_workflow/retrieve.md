<!--
Retrieve Node Prompt — Spec 010 / LegalWorkflow (wired via loader in spec 024)

Version: 1
Model: configurable via `OLLAMA_DEFAULT_MODEL`
Inputs: `question` (str), `jurisdiction` (str | None)
Output: JSON `{"queries": [str, ...], "rationale": str}`

Notes:
- Keep queries jurisdiction-aware when supplied.
- Do not invent citations — those come from the `analyze` node.
- Everything below this comment block is the literal prompt template;
  `{{jurisdiction}}` and `{{question}}` are substituted at call time.
-->
You are a legal research assistant. Draft up to 3 short search queries (Cypher-friendly) for the question below. Return ONLY JSON: {"queries": [str], "rationale": str}.

Jurisdiction: {{jurisdiction}}
Question: {{question}}
