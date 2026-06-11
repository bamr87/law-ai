<!--
Analyze Node Prompt — Spec 010 / LegalWorkflow (wired via loader in spec 024)

Version: 1
Model: configurable via `OLLAMA_DEFAULT_MODEL`
Inputs: `question` (str), `passages` (rendered list of {title, snippet, source_url})
Output: JSON `{"answer": str, "citations": [{"text": str, "source_url": str | null}], "confidence": float}`

Refusal policy:
- If retrieved passages are insufficient, return `confidence <= 0.4` and an
  `answer` that begins with "Insufficient sources to answer confidently:".
- Everything below this comment block is the literal prompt template;
  `{{question}}` and `{{passages}}` are substituted at call time.
-->
Answer the question using ONLY the passages below. Cite every legal proposition. Return strict JSON with keys answer, citations (array of {text, source_url}), confidence (0..1).

Question: {{question}}

Passages:
{{passages}}
