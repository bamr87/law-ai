# LSAT Argumentative Writing — prompt authoring

You are writing one new LSAT Argumentative Writing task for a practice library. The task presents a genuinely debatable issue, the principal positions in play, and several stated perspectives; the test taker argues for one position, answers the other, and is read against a rubric.

Everything you write is original. Do not reproduce, paraphrase, or lightly edit any real LSAT material or any exemplar shown to you — the exemplar is there to fix the *shape and register*, never the content.

## What makes this task good

- **The issue is genuinely open.** Both positions must be defensible by a reasonable person. If one side is obviously right, the task tests nothing.
- **The constraints are explicit.** State what cannot be done (the budget cannot be split, the deadline cannot move) so a writer must argue the tradeoff instead of dissolving it.
- **The perspectives do work.** Four short stated views, attributed to roles rather than named individuals. At least one must cut against each position, and they must not all point the same way.
- **The model response argues, then answers.** It takes exactly one position, gives a warrant for it, states the strongest case against it in that case's own strongest form, and answers *that*. It never simply restates the thesis louder.
- **The self-checks are checkable.** Each is a yes/no question a learner can honestly answer about their own draft, tied to a rubric criterion id.
- **No essay padding.** The model response is a tight 350-550 words. Length is not quality.

## Hard requirements

- At least two positions, each with `id`, `name`, and a one-sentence `summary`.
- At least three perspectives, each with `id` and `text`.
- `model_response.position_id` must be one of your position ids.
- Every `self_check[].criterion_id` and every `model_response.annotations[].criterion_id` must be a criterion id from the rubric shown below.
- Tag `concepts` only with ids from the concept catalog shown below.
- Write at the requested difficulty; do not drift easier.

## Output

Respond with a single JSON object and nothing else — no preamble, no markdown fences. The `drafts` array holds exactly the requested number of prompts (normally one):

```json
{
  "drafts": [
    {
      "title": "short descriptive title",
      "issue": "the debatable question in one sentence",
      "context": "background framing the debate, including the binding constraints",
      "positions": [
        {"id": "position-a", "name": "…", "summary": "…"},
        {"id": "position-b", "name": "…", "summary": "…"}
      ],
      "perspectives": [
        {"id": "perspective-1", "text": "a stated consideration, attributed to a role"}
      ],
      "task": "the instruction shown to the test taker",
      "prewriting_minutes": 15,
      "time_limit_minutes": 35,
      "concepts": ["concept-id"],
      "model_response": {
        "position_id": "position-a",
        "thesis": "one sentence",
        "essay": "350-550 words",
        "annotations": [{"criterion_id": "…", "note": "where the essay earns this criterion"}]
      },
      "self_check": [{"criterion_id": "…", "prompt": "a yes/no question about your own draft"}]
    }
  ]
}
```

Omit `id`, `rubric_id`, `difficulty`, and `source` — the platform owns them.
