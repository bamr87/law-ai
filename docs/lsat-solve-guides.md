# LSAT Solve Guides

A **solve guide** walks one bank question: the steps a strong solver takes, in order, with the board they build as they go. It is not a library article — an article explains a pattern across many questions, a guide is the worked instance of one ([docs/lsat-library.md](lsat-library.md) is the prose layer). They are maintained the same way, through the same HITL proposal queue, which is why the two runbooks used to share a page; this one is the guide half (BL-20260905-55).

Introduced by [specs/045-lsat-solving-aids](../specs/045-lsat-solving-aids/spec.md).

## Where it lives

| Thing | Path |
| ----- | ---- |
| Guides | `backend/law_ai/lsat/services/data/guides.json` |
| Models, loader, content lint | `backend/law_ai/lsat/services/guides.py` |
| API | `backend/law_ai/lsat/urls.py` → `/api/lsat/guides/*` |
| Author agent | `backend/law_ai/agents_runtime/crews/lsat_solve_guide_author.py` |
| Judge-tier reviewer | `backend/law_ai/agents_runtime/crews/lsat_guide_reviewer.py` |
| Backfill command | `backend/law_ai/lsat/management/commands/lsat_guide_backfill.py` |
| Promotion | `promote_guide_to_bank` in `backend/law_ai/lsat/services/proposals.py` |
| Tests | `backend/tests/lsat/test_guides.py`, `test_guide_backfill.py` |

## The backfill runbook

Coverage is the problem: 40 of 208 bank questions carry a guide, so most of the published site still shows "No step-by-step guide for this question yet." (LR is short 80, RC 55, LG 33). `lsat_guide_backfill` closes it in reviewed batches:

```bash
# What would be drafted, and how many are left. No provider needed.
make lsat-guide-backfill ARGS='--dry-run'

# Draft a batch. Needs a provider: `make claude-login`, ANTHROPIC_API_KEY, or
# LLM_PROVIDER_CHAIN=ollama for a local-only run.
make lsat-guide-backfill SECTION=LR LIMIT=20

# Then review every draft on the Authoring tab and approve or reject it,
# and refresh the offline site once the batch is in.
make lsat-export
```

A question that already carries a guide, or already sits in the queue, is never offered twice, so batches can be run back to back without duplicating work. Degraded offline-fallback drafts are skipped by default — they carry no walkthrough and would only cost a reviewer time; `--include-degraded` records them anyway for audit visibility.

The run is deliberately **operator-triggered**: 168 drafts is real model spend and, more to the point, real review time, and guide quality is only lint-checked. `backend/tests/lsat/test_guide_backfill.py` exercises the whole loop — draft, approve, serve, and skip on the next run — against a stubbed provider, so the machinery is verified without spending anything.

## Review and the judge tier

Each draft lands as a **pending `guide` proposal**. Two things run before a human sees it, and neither of them promotes anything:

1. `validate_guide_quality` (`guides.py`) — the deterministic content lint that runs at every choke point a guide passes through: draft parsing, promotion, and content load. It fails a guide that does not end with an answer step, whose answer step never names the keyed choice, that leaks the answer before it (spoiler discipline), or whose board contradicts itself (a sequence step that references an unknown entity, a grid cell outside the declared rows and columns).
2. `LSATGuideReviewer` (BL-20260830-15) — the judge-tier pedagogical pass. Its verdict (`pass`, `revise`, `reject`, or `unreviewed` when no provider answered) rides on the proposal's `meta.review` and renders in the Authoring queue as the "Pedagogical review" panel. Advisory: `unreviewed` must never read as approval, and a `pass` promotes nothing.

## Promotion

Approving a `guide` proposal calls `promote_guide_to_bank`, which re-validates the draft against its bank question, appends it to `guides.json`, and resets the guide cache so it serves immediately. A guide drafted beside a question that is *itself* still pending names that question's **proposal** id in `meta.guide_for_proposal`; promoting the question rewrites the link to the new bank id (`link_guides_to_question`), so the pair reaches the reviewer together rather than as two unrelated rows.

Nothing an agent drafts reaches a learner without a human promoting a specific proposal id. **After any guide is promoted, run `make lsat-export`** — `tests/test_lsat_site.py` fails CI when the committed `lsat-static/content.json` lags the source.
